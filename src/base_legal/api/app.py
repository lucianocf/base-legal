"""HTTP API and local web UI (thin adapter over the library; ARCHITECTURE §1).

Security properties (docs/THREAT_MODEL.md):

* binds to localhost by default (``base-legal serve``); optional API key (S9);
* input limits: question length, ``k`` (S6, LLM10) and a per-client rate
  limit on the endpoints that do work;
* strict CSP and security headers on every response; the UI loads only its
  own static files and renders model/corpus text with ``textContent`` (S11);
* questions are redacted before any third-party call, and are never logged
  (the request log carries method, path, status and timing only);
* every JSON body carries the "not legal advice" disclaimer, errors included.
"""

from __future__ import annotations

import hmac
import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from importlib import resources
from typing import Protocol

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from base_legal.config import Settings
from base_legal.corpus.ids import is_valid_id
from base_legal.corpus.models import Provision
from base_legal.generation.answer import DISCLAIMER, Answer, ProvisionView
from base_legal.privacy.redact import redact
from base_legal.retrieval.search import SearchResult
from base_legal.wiring import GenerationUnavailableError

log = logging.getLogger("base_legal.api")

MAX_K = 20
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Base-Legal-Notice": "not legal advice",
}
STATIC_TYPES = {".js": "text/javascript", ".css": "text/css"}


class Backend(Protocol):
    """What the API needs from the library (a fake in unit tests)."""

    def search(self, question: str, k: int) -> SearchResult: ...

    def answer(self, question: str) -> Answer: ...

    def provision(self, provision_id: str) -> Provision | None: ...

    def health(self) -> dict[str, str]: ...


# -- request and response models ---------------------------------------------


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


MAX_QUESTION_CHARS = 20_000  # hard cap; the configured limit (default 2000) is checked too


class QuestionBody(_Body):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class SearchBody(QuestionBody):
    k: int | None = Field(default=None, ge=1, le=MAX_K)


class SearchResponseHit(BaseModel):
    provision: ProvisionView
    score: float
    explicit: bool


class SearchResponse(BaseModel):
    hits: list[SearchResponseHit]
    missing_references: list[str]
    refusal: str | None
    redactions: dict[str, int]
    disclaimer: str = DISCLAIMER


class ProvisionResponse(BaseModel):
    provision: ProvisionView
    document_id: str
    amendments: list[str]
    disclaimer: str = DISCLAIMER


class HealthResponse(BaseModel):
    status: str
    index: dict[str, str]
    disclaimer: str = DISCLAIMER


# -- rate limiting -------------------------------------------------------------


class RateLimiter:
    """Sliding one-minute window per client address, in memory (single process)."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_minute = per_minute
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = self.clock()
        with self._lock:
            hits = self._hits[client]
            while hits and hits[0] <= now - 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True


# -- application ---------------------------------------------------------------


def create_app(
    backend: Backend,
    settings: Settings | None = None,
    limiter: RateLimiter | None = None,
) -> FastAPI:
    config: Settings = settings or Settings()
    limiter = limiter or RateLimiter(config.rate_limit_per_minute)
    max_chars = config.max_question_chars

    app = FastAPI(
        title="Base Legal",
        summary="Verified-citation Q&A over Brazilian data protection law. Not legal advice.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    @app.middleware("http")
    async def headers_and_access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith(("/ask", "/search", "/provisions", "/health")):
            response.headers.setdefault("Cache-Control", "no-store")
        # Content-free access log: never the body, never a query string.
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"detail": error.detail, "disclaimer": DISCLAIMER},
            status_code=error.status_code,
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        # Report where and why, never echo the submitted input back.
        details = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in error.errors()
        ]
        return JSONResponse({"detail": details, "disclaimer": DISCLAIMER}, status_code=422)

    def authorized(request: Request) -> None:
        expected = config.api_key
        if expected is None:
            return
        given = request.headers.get("x-api-key", "")
        if not hmac.compare_digest(given.encode(), expected.get_secret_value().encode()):
            raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")

    def rate_limited(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(
                status_code=429, detail="rate limit exceeded", headers={"Retry-After": "60"}
            )

    def check_length(question: str) -> None:
        if len(question) > max_chars:
            raise HTTPException(
                status_code=422, detail=f"question longer than {max_chars} characters"
            )

    guarded = [Depends(authorized), Depends(rate_limited)]

    @app.post("/ask", dependencies=guarded)
    def ask(body: QuestionBody) -> Answer:
        """Answer with verified citations, or refuse with the nearest provisions."""
        check_length(body.question)
        try:
            return backend.answer(body.question)
        except GenerationUnavailableError as error:
            raise HTTPException(
                status_code=503, detail=f"generation unavailable: {error}"
            ) from None

    @app.post("/search", dependencies=guarded)
    def search(body: SearchBody) -> SearchResponse:
        """Retrieve provisions (no LLM involved). The question is redacted first."""
        check_length(body.question)
        redacted = redact(body.question)
        result = backend.search(redacted.text, body.k or config.top_k)
        refusal = result.refusal(config.refusal_threshold)
        return SearchResponse(
            hits=[
                SearchResponseHit(
                    provision=ProvisionView.of(h.provision), score=h.score, explicit=h.explicit
                )
                for h in result.hits
            ],
            missing_references=list(result.missing_references),
            refusal=refusal.value if refusal else None,
            redactions=redacted.counts,
        )

    @app.get("/provisions/{provision_id}", dependencies=[Depends(authorized)])
    def provision(provision_id: str) -> ProvisionResponse:
        """One provision by canonical ID (e.g. ``lgpd:art7:incIX``)."""
        if not is_valid_id(provision_id):
            raise HTTPException(status_code=422, detail="not a canonical provision id")
        found = backend.provision(provision_id)
        if found is None:
            raise HTTPException(status_code=404, detail="provision not in the corpus")
        return ProvisionResponse(
            provision=ProvisionView.of(found),
            document_id=found.document_id,
            amendments=list(found.amendments),
        )

    @app.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", index=backend.health())

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> HTMLResponse:
        return HTMLResponse(_static("index.html"))

    @app.get("/static/{name}", include_in_schema=False)
    def static(name: str) -> Response:
        suffix = name[name.rfind(".") :] if "." in name else ""
        if name not in {"app.js", "style.css"}:
            raise HTTPException(status_code=404, detail="not found")
        return Response(_static(name), media_type=STATIC_TYPES[suffix])

    return app


def _static(name: str) -> str:
    return resources.files("base_legal.api").joinpath("static", name).read_text("utf-8")
