"""Deterministic red-team checks (``evals/redteam.yaml``); no model calls, no secrets.

Each case pairs the end-to-end expectation (checked locally, with the model)
with checks that CI can run on every pull request: PII redaction, citation
validation, nonexistent references, retrieval refusal, prompt isolation,
API input limits and text-only rendering in the UI.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field

from base_legal.corpus.models import Provision, ProvisionKind
from base_legal.corpus.xrefs import CrossReference
from base_legal.generation.answer import Answer, RefusalCause, Status
from base_legal.generation.prompt import SYSTEM_PROMPT, build_messages, system_blocks
from base_legal.grounding.validator import Citation, check_citation
from base_legal.privacy.redact import redact
from base_legal.retrieval.refs import candidate_ids, find_references
from base_legal.retrieval.search import SearchResult


class CheckType(StrEnum):
    REDACTION = "redaction"
    VALIDATOR = "validator"
    MISSING_REFERENCE = "missing_reference"
    REFUSAL = "refusal"
    PROMPT_ISOLATION = "prompt_isolation"
    API_LIMIT = "api_limit"
    UI_TEXT = "ui_text"


class CitationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provision_id: str
    quote: str


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: CheckType
    contains: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()
    provision: str | None = None
    citations: tuple[CitationSpec, ...] = ()
    issue: str | None = None
    status: int | None = None


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    owasp: tuple[str, ...]
    input: str
    expect: str
    checks: tuple[Check, ...]
    status: Literal["unverified", "verified"]
    length: int | None = Field(default=None, ge=1)
    poisoned_provision: str | None = None


class RedTeamSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    cases: tuple[Case, ...]

    @classmethod
    def load(cls, path: Path) -> RedTeamSet:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class Outcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    case: str
    check: CheckType
    outcome: Outcome
    detail: str = ""


class RedTeamReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: tuple[CheckResult, ...]

    @property
    def passed(self) -> int:
        return sum(r.outcome is Outcome.PASSED for r in self.results)

    @property
    def failed(self) -> int:
        return sum(r.outcome is Outcome.FAILED for r in self.results)

    @property
    def pass_rate(self) -> float:
        ran = self.passed + self.failed
        return self.passed / ran if ran else 0.0


class Searcher(Protocol):
    def search(self, question: str, k: int = 8) -> SearchResult: ...


def synthetic_cpf(rng: random.Random) -> str:
    """A random CPF with valid check digits (test data; generated, never hardcoded)."""
    while True:
        digits = [rng.randrange(10) for _ in range(9)]
        if len(set(digits)) > 1:
            break
    for position in (9, 10):
        total = sum(d * (position + 1 - i) for i, d in enumerate(digits))
        digits.append(total * 10 % 11 % 10)
    s = "".join(map(str, digits))
    return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"


def run_redteam(
    cases: Sequence[Case],
    corpus: Mapping[str, Provision],
    *,
    searcher: Searcher | None = None,
    threshold: float | None = None,
    seed: int | None = None,
) -> RedTeamReport:
    rng = random.Random(seed)  # noqa: S311 - synthetic test data, not security
    results: list[CheckResult] = []
    for case in cases:
        values = {"{cpf}": synthetic_cpf(rng), "{long}": "a" * (case.length or 1)}

        def fill(text: str, values: dict[str, str] = values) -> str:
            for key, value in values.items():
                text = text.replace(key, value)
            return text

        text = fill(case.input)
        for check in case.checks:
            outcome, detail = _run_check(check, case, text, fill, corpus, searcher, threshold)
            results.append(
                CheckResult(case=case.id, check=check.type, outcome=outcome, detail=detail)
            )
    return RedTeamReport(results=tuple(results))


def _run_check(
    check: Check,
    case: Case,
    text: str,
    fill: Callable[[str], str],
    corpus: Mapping[str, Provision],
    searcher: Searcher | None,
    threshold: float | None,
) -> tuple[Outcome, str]:
    match check.type:
        case CheckType.REDACTION:
            redacted = redact(text).text
            missing = [c for c in map(fill, check.contains) if c not in redacted]
            leaked = [a for a in map(fill, check.absent) if a in redacted]
            if missing or leaked:
                return Outcome.FAILED, f"missing={len(missing)} leaked={len(leaked)}"
            return Outcome.PASSED, ""
        case CheckType.VALIDATOR:
            issues = [
                check_citation(Citation(c.provision_id, c.quote), corpus) for c in check.citations
            ]
            got = [i.value if i else None for i in issues]
            ok = all(g == check.issue for g in got)
            return (Outcome.PASSED if ok else Outcome.FAILED), f"issues={got}"
        case CheckType.MISSING_REFERENCE:
            missing = [
                group[-1]
                for group in map(candidate_ids, find_references(text))
                if not any(c in corpus for c in group)
            ]
            ok = check.provision in missing
            return (Outcome.PASSED if ok else Outcome.FAILED), f"missing={missing}"
        case CheckType.REFUSAL:
            if searcher is None:
                return Outcome.SKIPPED, "needs the retrieval index (run with a database)"
            refusal = searcher.search(redact(text).text).refusal(threshold)
            return (Outcome.PASSED if refusal else Outcome.FAILED), f"refusal={refusal}"
        case CheckType.PROMPT_ISOLATION:
            return _prompt_isolation(case, text, corpus)
        case CheckType.API_LIMIT:
            return _api_limit(text, check.status or 422)
        case CheckType.UI_TEXT:
            return _ui_text()


def _prompt_isolation(
    case: Case, text: str, corpus: Mapping[str, Provision]
) -> tuple[Outcome, str]:
    if case.poisoned_provision:
        provision = Provision(
            id="lgpd:art7:incI",
            document_id="lgpd",
            parent_id=None,
            kind=ProvisionKind.INCISO,
            label="I",
            text=case.poisoned_provision,
            path=("Art. 7º", "I"),
            ordinal=0,
        )
    else:
        provision = corpus.get("lgpd:art7:incI") or next(iter(corpus.values()))
    question = redact(text).text
    (turn,) = build_messages(question, [provision], {})
    *documents, question_block = turn["content"]
    problems = []
    if [b["text"] for b in system_blocks()] != [SYSTEM_PROMPT] or provision.text in SYSTEM_PROMPT:
        problems.append("system prompt is not the static, input-independent constant")
    if len(documents) != 1 or documents[0]["type"] != "document":
        problems.append("provision not sent as a document")
    elif documents[0]["source"]["content"] != [{"type": "text", "text": provision.text}]:
        problems.append("document content is not exactly the provision text")
    if question_block["text"] != f"<pergunta>\n{question}\n</pergunta>":
        problems.append("question not isolated in its own block")
    if provision.text in question_block["text"] and provision.text not in question:
        problems.append("provision text leaked into the question block")
    return (Outcome.FAILED, "; ".join(problems)) if problems else (Outcome.PASSED, "")


class _NoWorkBackend:
    """Fails the check if the API does any work for an input it must reject."""

    def __init__(self) -> None:
        self.calls = 0

    def search(self, question: str, k: int) -> SearchResult:
        self.calls += 1
        return SearchResult(hits=(), best_similarity=None)

    def answer(self, question: str) -> Answer:
        self.calls += 1  # reaching this means the input was accepted: the check fails
        return Answer(status=Status.REFUSED, refusal=RefusalCause.LOW_SCORE)

    def provision(self, provision_id: str) -> Provision | None:
        return None

    def references(self, texts: Mapping[str, str]) -> dict[str, tuple[CrossReference, ...]]:
        return {}

    def health(self) -> dict[str, str]:
        return {}


def _api_limit(text: str, status: int) -> tuple[Outcome, str]:
    from fastapi.testclient import TestClient

    from base_legal.api.app import create_app
    from base_legal.config import Settings

    backend = _NoWorkBackend()
    client = TestClient(create_app(backend, Settings()))
    response = client.post("/ask", json={"question": text})
    ok = response.status_code == status and backend.calls == 0
    return (Outcome.PASSED if ok else Outcome.FAILED), f"status={response.status_code}"


def _ui_text() -> tuple[Outcome, str]:
    from fastapi.testclient import TestClient

    from base_legal.api.app import create_app

    client = TestClient(create_app(_NoWorkBackend()))
    page, script = client.get("/"), client.get("/static/app.js")
    csp = page.headers.get("content-security-policy", "")
    problems = []
    if "script-src 'self'" not in csp or "unsafe-inline" in csp:
        problems.append("CSP allows inline scripts")
    if re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page.text, re.IGNORECASE):
        problems.append("inline script in the page")
    code = re.sub(r"//.*", "", script.text)  # comments may mention what is forbidden
    if re.search(r"\binnerHTML\b|insertAdjacentHTML|outerHTML|document\.write", code):
        problems.append("HTML sink in app.js")
    return (Outcome.FAILED, "; ".join(problems)) if problems else (Outcome.PASSED, "")


def to_markdown(report: RedTeamReport, cases: Sequence[Case]) -> str:
    owasp = {c.id: ", ".join(c.owasp) for c in cases}
    lines = [
        "# Red-team eval (deterministic checks)",
        "",
        f"Pass rate: **{100 * report.pass_rate:.1f} %** ({report.passed} passed, "
        f"{report.failed} failed, {len(report.results) - report.passed - report.failed} skipped)",
        "",
        "| Case | OWASP | Check | Outcome | Detail |",
        "|---|---|---|---|---|",
    ]
    for r in report.results:
        cells = (r.case, owasp.get(r.case, ""), r.check.value, r.outcome.value, r.detail)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
