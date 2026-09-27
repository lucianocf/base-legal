import logging
import re
from importlib import resources

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from base_legal.api.app import CSP, RateLimiter, create_app
from base_legal.config import Settings
from base_legal.corpus.models import Provision, ProvisionKind
from base_legal.generation.answer import (
    DISCLAIMER,
    Answer,
    AnswerPart,
    CitedQuote,
    ProvisionView,
    Status,
)
from base_legal.retrieval.search import Hit, SearchResult
from base_legal.wiring import GenerationUnavailableError

ART7_IX = Provision(
    id="lgpd:art7:incIX",
    document_id="lgpd",
    parent_id="lgpd:art7",
    kind=ProvisionKind.INCISO,
    label="IX",
    text="quando necessário para atender aos interesses legítimos do controlador;",
    path=("Art. 7º", "IX"),
    ordinal=1,
)


class _Backend:
    def __init__(self) -> None:
        self.asked: list[str] = []
        self.searched: list[tuple[str, int]] = []
        self.unavailable = False

    def search(self, question: str, k: int) -> SearchResult:
        self.searched.append((question, k))
        return SearchResult(hits=(Hit(ART7_IX, 0.9),), best_similarity=0.8)

    def answer(self, question: str) -> Answer:
        self.asked.append(question)
        if self.unavailable:
            raise GenerationUnavailableError("no Anthropic credentials")
        return Answer(
            status=Status.ANSWERED,
            parts=(
                AnswerPart(
                    text="Pode, com legítimo interesse.",
                    citations=(CitedQuote(provision_id=ART7_IX.id, quote=ART7_IX.text),),
                ),
            ),
            provisions=(ProvisionView.of(ART7_IX),),
        )

    def provision(self, provision_id: str) -> Provision | None:
        return ART7_IX if provision_id == ART7_IX.id else None

    def health(self) -> dict[str, str]:
        return {"embedding_family": "voyage-4"}


@pytest.fixture
def backend() -> _Backend:
    return _Backend()


@pytest.fixture
def client(backend: _Backend) -> TestClient:
    return TestClient(create_app(backend, Settings(rate_limit_per_minute=1000)))


def test_health_has_disclaimer_and_security_headers(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "index": {"embedding_family": "voyage-4"},
        "disclaimer": DISCLAIMER,
    }
    assert response.headers["content-security-policy"] == CSP
    assert "script-src 'self'" in CSP
    assert "'unsafe-inline'" not in CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-base-legal-notice"] == "not legal advice"


def test_ask(client: TestClient, backend: _Backend) -> None:
    response = client.post("/ask", json={"question": "Posso usar legítimo interesse?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["parts"][0]["citations"][0]["provision_id"] == "lgpd:art7:incIX"
    assert body["disclaimer"] == DISCLAIMER
    assert backend.asked == ["Posso usar legítimo interesse?"]  # Answerer redacts


def test_oversized_question_is_rejected_before_any_work(
    client: TestClient, backend: _Backend
) -> None:
    # Red-team t10: a 50,000-character question gets HTTP 422 before any API call.
    response = client.post("/ask", json={"question": "a" * 50_000})
    assert response.status_code == 422
    body = response.json()
    assert body["disclaimer"] == DISCLAIMER
    assert "aaaa" not in response.text  # the input is never echoed back
    assert backend.asked == []
    configured = client.post("/ask", json={"question": "b" * 2001})  # default limit: 2000
    assert configured.status_code == 422
    assert "longer than 2000" in configured.text
    assert backend.asked == []


@pytest.mark.parametrize(
    "payload",
    [{"question": ""}, {}, {"question": "ok", "extra": 1}, {"question": 42}],
)
def test_invalid_bodies(client: TestClient, payload: dict[str, object]) -> None:
    response = client.post("/ask", json=payload)
    assert response.status_code == 422
    assert response.json()["disclaimer"] == DISCLAIMER


def test_search_redacts_before_the_backend_and_limits_k(
    client: TestClient, backend: _Backend
) -> None:
    response = client.post(
        "/search", json={"question": "Meu e-mail é ana@example.com; art. 7, IX", "k": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["redactions"] == {"EMAIL": 1}
    assert body["hits"][0]["provision"]["id"] == "lgpd:art7:incIX"
    assert body["refusal"] is None
    assert backend.searched == [("Meu e-mail é [EMAIL_1]; art. 7, IX", 5)]
    assert client.post("/search", json={"question": "x", "k": 21}).status_code == 422
    assert client.post("/search", json={"question": "x", "k": 0}).status_code == 422


def test_provisions(client: TestClient) -> None:
    ok = client.get("/provisions/lgpd:art7:incIX")
    assert ok.status_code == 200
    assert ok.json()["provision"]["text"] == ART7_IX.text
    assert ok.json()["disclaimer"] == DISCLAIMER
    missing = client.get("/provisions/lgpd:art99")
    assert missing.status_code == 404
    assert missing.json()["disclaimer"] == DISCLAIMER
    assert client.get("/provisions/not-an-id").status_code == 422


def test_generation_unavailable_is_503(client: TestClient, backend: _Backend) -> None:
    backend.unavailable = True
    response = client.post("/ask", json={"question": "pergunta"})
    assert response.status_code == 503
    assert response.json()["detail"] == "generation unavailable: no Anthropic credentials"


def test_rate_limit(backend: _Backend) -> None:
    now = [0.0]
    app = create_app(backend, Settings(), RateLimiter(2, clock=lambda: now[0]))
    client = TestClient(app)
    assert client.post("/search", json={"question": "a"}).status_code == 200
    assert client.post("/ask", json={"question": "a"}).status_code == 200
    limited = client.post("/ask", json={"question": "a"})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert limited.json()["disclaimer"] == DISCLAIMER
    assert client.get("/health").status_code == 200  # cheap endpoints are not limited
    now[0] = 61.0
    assert client.post("/ask", json={"question": "a"}).status_code == 200


def test_optional_api_key(backend: _Backend) -> None:
    client = TestClient(create_app(backend, Settings(api_key=SecretStr("s3cret-key"))))
    assert client.post("/ask", json={"question": "a"}).status_code == 401
    assert client.get("/provisions/lgpd:art7:incIX").status_code == 401
    ok = client.post("/ask", json={"question": "a"}, headers={"X-API-Key": "s3cret-key"})
    assert ok.status_code == 200
    assert client.get("/health").status_code == 200


def test_logs_never_contain_question_text(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    question = "Meu irmão Carlos tem diabetes e mora na Rua das Flores 12; posso contar?"
    with caplog.at_level(logging.DEBUG):
        client.post("/ask", json={"question": question})
        client.post("/search", json={"question": question})
        client.post("/ask", json={"question": question + "x" * 3000})
    assert caplog.records
    dumped = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    for fragment in ("Carlos", "diabetes", "Flores"):
        assert fragment not in dumped


def test_ui_renders_text_only_and_has_no_inline_code(client: TestClient) -> None:
    # Red-team t09: model/corpus text is rendered as text; CSP blocks inline scripts.
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["content-security-policy"] == CSP
    html = page.text
    assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html) is None  # no inline script
    assert "style=" not in html
    assert " on" + "click=" not in html
    js = client.get("/static/app.js")
    assert js.headers["content-type"].startswith("text/javascript")
    assert "innerHTML" not in js.text.replace("never innerHTML", "")
    assert "insertAdjacentHTML" not in js.text
    assert "eval(" not in js.text
    assert "textContent" in js.text
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/../app.py").status_code == 404
    assert client.get("/static/other.js").status_code == 404


def test_static_files_are_packaged() -> None:
    names = {p.name for p in resources.files("base_legal.api").joinpath("static").iterdir()}
    assert {"index.html", "app.js", "style.css"} <= names
