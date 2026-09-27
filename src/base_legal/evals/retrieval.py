"""Retrieval evaluation on the golden set: recall@k, MRR, refusals, latency.

Questions go through the production path (PII redaction, then
:class:`~base_legal.retrieval.search.Retriever`), so the numbers describe what
users get. Nothing here calls a paid API: questions are embedded locally.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from base_legal.evals.golden import GoldenSet, Split
from base_legal.evals.metrics import (
    first_rank,
    hit_at_k,
    mean,
    percentile,
    recall_at_k,
    reciprocal_rank,
)
from base_legal.privacy.redact import redact
from base_legal.retrieval.search import SearchResult

KS = (1, 5, 10)


class Searcher(Protocol):
    def search(self, question: str, k: int = 8) -> SearchResult: ...


class AnswerableResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    expected: tuple[str, ...]
    ranked: tuple[str, ...]
    first_rank: int | None
    refused: str | None
    best_similarity: float | None
    latency_ms: float


class RefuseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    reason: str
    refused: str | None
    top: tuple[str, ...]
    best_similarity: float | None
    latency_ms: float


class Metrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    answerable: int
    refuse: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    hit_at_5: float
    mrr: float
    refusal_accuracy: float | None
    false_refusal_rate: float
    latency_p50_ms: float
    latency_p95_ms: float


class RetrievalReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    split: Split
    config: dict[str, str]
    metrics: Metrics
    answerable: tuple[AnswerableResult, ...]
    refuse: tuple[RefuseResult, ...]


def evaluate(
    searcher: Searcher,
    golden: GoldenSet,
    *,
    split: Split,
    threshold: float | None,
    label: str,
    config: dict[str, str] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> RetrievalReport:
    selected = golden.select(split)
    depth = max(KS)
    latencies: list[float] = []

    def run(question: str) -> tuple[SearchResult, float]:
        start = clock()
        result = searcher.search(redact(question).text, k=depth)
        elapsed = (clock() - start) * 1000
        latencies.append(elapsed)
        return result, elapsed

    answerable: list[AnswerableResult] = []
    for item in selected.answerable:
        result, elapsed = run(item.question)
        ranked = tuple(h.provision.id for h in result.hits)
        refused = result.refusal(threshold)
        answerable.append(
            AnswerableResult(
                id=item.id,
                expected=item.expected,
                ranked=ranked,
                first_rank=first_rank(item.expected, ranked),
                refused=refused.value if refused else None,
                best_similarity=result.best_similarity,
                latency_ms=round(elapsed, 2),
            )
        )

    refuse: list[RefuseResult] = []
    for must_refuse in selected.refuse:
        result, elapsed = run(must_refuse.question)
        refused = result.refusal(threshold)
        refuse.append(
            RefuseResult(
                id=must_refuse.id,
                reason=must_refuse.reason.value,
                refused=refused.value if refused else None,
                top=tuple(h.provision.id for h in result.hits[:3]),
                best_similarity=result.best_similarity,
                latency_ms=round(elapsed, 2),
            )
        )

    return RetrievalReport(
        label=label,
        split=split,
        config={"threshold": str(threshold), **(config or {})},
        metrics=_metrics(answerable, refuse, latencies),
        answerable=tuple(answerable),
        refuse=tuple(refuse),
    )


def _effective(result: AnswerableResult) -> tuple[str, ...]:
    # A refused answer shows the user no provisions as an answer.
    return () if result.refused else result.ranked


def _metrics(
    answerable: Sequence[AnswerableResult],
    refuse: Sequence[RefuseResult],
    latencies: Sequence[float],
) -> Metrics:
    def recall(k: int) -> float:
        return round(mean([recall_at_k(r.expected, _effective(r), k) for r in answerable]), 4)

    return Metrics(
        answerable=len(answerable),
        refuse=len(refuse),
        recall_at_1=recall(1),
        recall_at_5=recall(5),
        recall_at_10=recall(10),
        hit_at_5=round(
            mean([float(hit_at_k(r.expected, _effective(r), 5)) for r in answerable]), 4
        ),
        mrr=round(mean([reciprocal_rank(r.expected, _effective(r)) for r in answerable]), 4),
        refusal_accuracy=(
            round(mean([float(r.refused is not None) for r in refuse]), 4) if refuse else None
        ),
        false_refusal_rate=round(mean([float(r.refused is not None) for r in answerable]), 4),
        latency_p50_ms=round(percentile(latencies, 50), 2) if latencies else 0.0,
        latency_p95_ms=round(percentile(latencies, 95), 2) if latencies else 0.0,
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f} %"


def to_markdown(report: RetrievalReport) -> str:
    m = report.metrics
    config = ", ".join(f"{k}={v}" for k, v in sorted(report.config.items()))
    lines = [
        f"# Retrieval eval: {report.label} ({report.split.value})",
        "",
        f"Config: {config}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Answerable questions | {m.answerable} |",
        f"| Must-refuse questions | {m.refuse} |",
        f"| recall@1 | {_pct(m.recall_at_1)} |",
        f"| recall@5 | {_pct(m.recall_at_5)} |",
        f"| recall@10 | {_pct(m.recall_at_10)} |",
        f"| hit@5 | {_pct(m.hit_at_5)} |",
        f"| MRR | {m.mrr:.3f} |",
        f"| Refusal accuracy (must-refuse) | {_pct(m.refusal_accuracy)} |",
        f"| False refusals (answerable) | {_pct(m.false_refusal_rate)} |",
        f"| Latency p50 / p95 | {m.latency_p50_ms:.0f} / {m.latency_p95_ms:.0f} ms |",
        "",
    ]
    misses = [r for r in report.answerable if r.first_rank is None or r.first_rank > 5 or r.refused]
    if misses:
        lines += ["## Answerable questions without an expected provision in the top 5", ""]
        lines += ["| Item | Expected | Top 3 | Refused |", "|---|---|---|---|"]
        for r in misses:
            lines.append(
                f"| {r.id} | {', '.join(r.expected)} | {', '.join(r.ranked[:3])} "
                f"| {r.refused or ''} |"
            )
        lines.append("")
    wrong = [r for r in report.refuse if r.refused is None]
    if wrong:
        lines += ["## Must-refuse questions that were answered", ""]
        lines += ["| Item | Reason | Top 3 | Best similarity |", "|---|---|---|---|"]
        for answered in wrong:
            best = "n/a" if answered.best_similarity is None else f"{answered.best_similarity:.3f}"
            lines.append(
                f"| {answered.id} | {answered.reason} | {', '.join(answered.top)} | {best} |"
            )
        lines.append("")
    return "\n".join(lines)
