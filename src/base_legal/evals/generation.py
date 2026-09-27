"""Generation eval: run the grounded answerer over the golden set.

Paid (every answerable question that passes retrieval calls Claude), so it is
never run in CI and the CLI requires an explicit ``--yes``. Reports carry IDs,
statuses, cited provision IDs, token counts and timings only: no question or
answer text (docs/PRIVACY.md). Compare models by running it twice with
different ``BASE_LEGAL_MODEL`` values.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from base_legal.evals.golden import GoldenSet, Split
from base_legal.generation.answer import Answer, Status, Usage


class AnswersQuestions(Protocol):
    def answer(self, question: str) -> Answer: ...


class GenerationItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: Literal["answerable", "refuse"]
    status: Status
    refusal: str | None
    cited: tuple[str, ...]
    expected: tuple[str, ...]
    citation_recall: float | None  # answerable items only
    latency_ms: float
    usage: Usage | None


class GenerationMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    answerable: int
    answered_rate: float
    citation_recall: float  # refused answerable items count as 0
    must_refuse: int
    refusal_accuracy: float
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    latency_p50_ms: float
    latency_p95_ms: float


class GenerationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    model: str
    split: Split
    metrics: GenerationMetrics
    items: tuple[GenerationItem, ...]


def covers(cited: str, expected: str) -> bool:
    """A citation supports an expected provision if it is that provision, a part of
    it, or the provision that contains it (``lgpd:art18`` and ``lgpd:art18:incV``)."""
    return cited == expected or cited.startswith(expected + ":") or expected.startswith(cited + ":")


def citation_recall(cited: Sequence[str], expected: Sequence[str]) -> float:
    return sum(any(covers(c, e) for c in cited) for e in expected) / len(expected)


def _item(
    item_id: str,
    kind: Literal["answerable", "refuse"],
    expected: tuple[str, ...],
    answer: Answer,
    latency_ms: float,
) -> GenerationItem:
    cited = tuple(dict.fromkeys(c.provision_id for p in answer.parts for c in p.citations))
    recall = None
    if kind == "answerable":
        recall = citation_recall(cited, expected) if answer.status is Status.ANSWERED else 0.0
    return GenerationItem(
        id=item_id,
        kind=kind,
        status=answer.status,
        refusal=answer.refusal.value if answer.refusal else None,
        cited=cited,
        expected=expected,
        citation_recall=recall,
        latency_ms=latency_ms,
        usage=answer.usage,
    )


def evaluate_generation(
    answerer: AnswersQuestions,
    golden: GoldenSet,
    *,
    split: Split,
    model: str,
    label: str,
    limit: int | None = None,
) -> GenerationReport:
    selected = golden.select(split)
    items: list[GenerationItem] = []
    work: list[tuple[str, Literal["answerable", "refuse"], str, tuple[str, ...]]] = [
        (i.id, "answerable", i.question, i.expected) for i in selected.answerable
    ] + [(i.id, "refuse", i.question, ()) for i in selected.refuse]
    for item_id, kind, question, expected in work[:limit]:
        started = time.perf_counter()
        answer = answerer.answer(question)
        items.append(_item(item_id, kind, expected, answer, (time.perf_counter() - started) * 1000))
    return GenerationReport(
        label=label, model=model, split=split, metrics=_metrics(items), items=tuple(items)
    )


def _metrics(items: Sequence[GenerationItem]) -> GenerationMetrics:
    answerable = [i for i in items if i.kind == "answerable"]
    refuse = [i for i in items if i.kind == "refuse"]
    usages = [i.usage for i in items if i.usage is not None]
    latencies = sorted(i.latency_ms for i in items) or [0.0]
    return GenerationMetrics(
        answerable=len(answerable),
        answered_rate=_mean([i.status is Status.ANSWERED for i in answerable]),
        citation_recall=_mean([i.citation_recall or 0.0 for i in answerable]),
        must_refuse=len(refuse),
        refusal_accuracy=_mean([i.status is Status.REFUSED for i in refuse]),
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        cache_read_input_tokens=sum(u.cache_read_input_tokens for u in usages),
        cache_creation_input_tokens=sum(u.cache_creation_input_tokens for u in usages),
        latency_p50_ms=statistics.median(latencies),
        latency_p95_ms=latencies[int(0.95 * (len(latencies) - 1))],
    )


def _mean(values: Sequence[float | bool]) -> float:
    return statistics.fmean(float(v) for v in values) if values else 0.0


def to_markdown(report: GenerationReport) -> str:
    m = report.metrics
    lines = [
        f"# Generation eval: {report.label}",
        "",
        f"Model: `{report.model}` · split: {report.split.value} · "
        "IDs and numbers only (no question or answer text).",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Answerable items answered | {100 * m.answered_rate:.1f} % of {m.answerable} |",
        f"| Citation recall (expected provisions cited) | {100 * m.citation_recall:.1f} % |",
        f"| Must-refuse items refused | {100 * m.refusal_accuracy:.1f} % of {m.must_refuse} |",
        f"| Input / output tokens | {m.input_tokens} / {m.output_tokens} |",
        f"| Cache read / creation tokens | {m.cache_read_input_tokens} / "
        f"{m.cache_creation_input_tokens} |",
        f"| Latency p50 / p95 | {m.latency_p50_ms:.0f} / {m.latency_p95_ms:.0f} ms |",
        "",
        "| Item | Status | Refusal | Cited | Expected |",
        "|---|---|---|---|---|",
    ]
    for i in report.items:
        lines.append(
            f"| {i.id} | {i.status.value} | {i.refusal or ''} | {', '.join(i.cited)} "
            f"| {', '.join(i.expected)} |"
        )
    return "\n".join(lines) + "\n"
