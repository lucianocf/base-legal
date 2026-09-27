import json
from pathlib import Path

import pytest

from base_legal.corpus.manifest import Manifest
from base_legal.corpus.models import Provision, ProvisionKind
from base_legal.corpus.pipeline import load_documents
from base_legal.evals.golden import GoldenSet, Split
from base_legal.evals.metrics import (
    first_rank,
    hit_at_k,
    mean,
    percentile,
    recall_at_k,
    reciprocal_rank,
)
from base_legal.evals.retrieval import evaluate, to_markdown
from base_legal.retrieval.search import Hit, RefusalReason, SearchResult

ROOT = Path(__file__).parents[2]


def test_metrics() -> None:
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(["b", "z"], ranked, 2) == 0.5
    assert recall_at_k(["b", "z"], ranked, 1) == 0.0
    assert hit_at_k(["z", "c"], ranked, 3)
    assert not hit_at_k(["z"], ranked, 4)
    assert first_rank(["c", "b"], ranked) == 2
    assert first_rank(["z"], ranked) is None
    assert reciprocal_rank(["c"], ranked) == pytest.approx(1 / 3)
    assert reciprocal_rank(["z"], ranked) == 0.0
    assert percentile([5, 1, 3, 2, 4], 50) == 3
    assert percentile([5, 1, 3, 2, 4], 95) == 5
    assert percentile([7], 0) == 7
    assert mean([]) == 0.0
    with pytest.raises(ValueError, match="empty"):
        recall_at_k([], ranked, 1)
    with pytest.raises(ValueError, match="no values"):
        percentile([], 50)
    with pytest.raises(ValueError, match="q must be"):
        percentile([1], 101)


def test_repo_golden_set_is_valid_and_matches_the_corpus() -> None:
    golden = GoldenSet.load(ROOT / "evals" / "golden.yaml")
    manifest = Manifest.load(ROOT / "corpus" / "manifest.yaml")
    known = {
        p.id
        for d in load_documents(ROOT / "corpus", manifest)
        for p in d.provisions
        if p.is_normative
    }
    assert golden.unknown_ids(known) == []
    assert len(golden.answerable) >= 40
    assert {i.status for i in (*golden.answerable, *golden.refuse)} == {"unverified"}
    dev, holdout = golden.select(Split.DEV), golden.select(Split.HOLDOUT)
    assert len(dev.answerable) + len(holdout.answerable) == len(golden.answerable)
    assert holdout.answerable
    assert holdout.refuse
    # The known failures that motivate tuning must never be in the holdout.
    assert {i.id for i in holdout.answerable}.isdisjoint({"g43", "g44"})


def test_golden_set_rejects_malformed_ids_and_duplicates(tmp_path: Path) -> None:
    bad = {
        "version": 1,
        "answerable": [
            {
                "id": "a",
                "question": "q",
                "expected": ["LGPD art 7"],
                "split": "dev",
                "status": "unverified",
            }
        ],
        "refuse": [],
    }
    path = tmp_path / "g.yaml"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        GoldenSet.load(path)
    dup = {
        "version": 1,
        "answerable": [],
        "refuse": [
            {
                "id": "r",
                "question": "q",
                "reason": "off_topic",
                "split": "dev",
                "status": "unverified",
            },
            {
                "id": "r",
                "question": "q2",
                "reason": "off_topic",
                "split": "dev",
                "status": "unverified",
            },
        ],
    }
    path.write_text(json.dumps(dup), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        GoldenSet.load(path)


def _provision(pid: str) -> Provision:
    return Provision(
        id=pid,
        document_id="lgpd",
        parent_id=None,
        kind=ProvisionKind.ARTICLE,
        label="Art.",
        text="texto",
        path=("Art.",),
        ordinal=0,
    )


class _FakeSearcher:
    """Answers from a table; records what it was asked (must be redacted)."""

    def __init__(self, table: dict[str, SearchResult]) -> None:
        self.table = table
        self.asked: list[str] = []

    def search(self, question: str, k: int = 8) -> SearchResult:
        self.asked.append(question)
        for key, result in self.table.items():
            if key in question:
                return result
        return SearchResult(hits=(), best_similarity=0.1)


def _result(*ids: str, best: float = 0.9, missing: tuple[str, ...] = ()) -> SearchResult:
    return SearchResult(
        hits=tuple(Hit(_provision(i), 1.0) for i in ids),
        best_similarity=best,
        missing_references=missing,
    )


def test_evaluate_computes_metrics_and_redacts_questions(tmp_path: Path) -> None:
    golden = GoldenSet.model_validate(
        {
            "version": 1,
            "answerable": [
                {
                    "id": "a1",
                    "question": "sensível? CPF 529.982.247-25",
                    "expected": ["lgpd:art5:incII"],
                    "split": "dev",
                    "status": "unverified",
                },
                {
                    "id": "a2",
                    "question": "portabilidade",
                    "expected": ["lgpd:art18:incV", "lgpd:art18"],
                    "split": "dev",
                    "status": "unverified",
                },
                {
                    "id": "h1",
                    "question": "holdout",
                    "expected": ["lgpd:art1"],
                    "split": "holdout",
                    "status": "unverified",
                },
            ],
            "refuse": [
                {
                    "id": "r1",
                    "question": "art. 99",
                    "reason": "nonexistent_provision",
                    "split": "dev",
                    "status": "unverified",
                },
                {
                    "id": "r2",
                    "question": "bolo",
                    "reason": "off_topic",
                    "split": "dev",
                    "status": "unverified",
                },
            ],
        }
    )
    searcher = _FakeSearcher(
        {
            "sensível": _result("lgpd:art5:incII", "lgpd:art11"),
            "portabilidade": _result("lgpd:art9", "lgpd:art18:incV", best=0.2),
            "art. 99": _result("lgpd:art9", missing=("lgpd:art99",)),
            "bolo": _result("lgpd:art1", best=0.3),
        }
    )
    ticks = iter(range(100))
    report = evaluate(
        searcher,
        golden,
        split=Split.DEV,
        threshold=0.5,
        label="t",
        clock=lambda: float(next(ticks)) / 1000,
    )
    assert all("529.982.247-25" not in q for q in searcher.asked)
    m = report.metrics
    assert (m.answerable, m.refuse) == (2, 2)
    assert m.recall_at_1 == 0.5  # a2 is refused (low score) so it counts as a miss
    assert m.mrr == 0.5
    assert m.false_refusal_rate == 0.5
    assert m.refusal_accuracy == 1.0
    assert m.latency_p50_ms == pytest.approx(1.0)
    markdown = to_markdown(report)
    assert "| recall@1 | 50.0 % |" in markdown
    assert "| a2 | lgpd:art18:incV, lgpd:art18 |" in markdown

    no_threshold = evaluate(searcher, golden, split=Split.DEV, threshold=None, label="t")
    assert no_threshold.metrics.refusal_accuracy == 0.5
    assert "Must-refuse questions that were answered" in to_markdown(no_threshold)
    assert (
        evaluate(searcher, golden, split=Split.ALL, threshold=None, label="t").metrics.answerable
        == 3
    )


def test_refusal_decision() -> None:
    explicit = SearchResult(
        hits=(Hit(_provision("lgpd:art7"), 1.0, explicit=True),),
        best_similarity=0.0,
        missing_references=("lgpd:art99",),
    )
    assert explicit.refusal(0.5) is None
    assert _result("lgpd:art1", missing=("lgpd:art99",)).refusal(None) is (
        RefusalReason.NONEXISTENT_PROVISION
    )
    assert _result("lgpd:art1", best=0.4).refusal(0.5) is RefusalReason.LOW_SCORE
    assert _result("lgpd:art1", best=0.4).refusal(None) is None
    assert SearchResult(hits=(), best_similarity=None).refusal(0.5) is RefusalReason.LOW_SCORE
