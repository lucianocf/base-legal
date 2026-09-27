"""Local reranker benchmark (ADR 0003, Phase 2): does a cross-encoder help?

Maintainer-only. Reranks the hybrid top-N of the shipped retriever with each
pinned, benchmark-only model and reports recall@5, MRR and CPU latency on the
golden dev and holdout splits, plus how well the best reranker score separates
answerable questions from must-refuse ones (a candidate refusal signal).
Questions never leave the machine: every model runs locally from pinned,
hash-verified weights (safetensors, no remote code).

    uv sync --extra local --extra bench
    DATABASE_URL=... uv run python benchmarks/rerank.py --depth 20 --models bge,minilm,qwen
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from base_legal.config import Settings
from base_legal.embeddings.model_store import fetch_model, load_lock_file
from base_legal.evals.golden import GoldenSet, RefuseReason, Split
from base_legal.retrieval.search import SearchResult
from base_legal.store.db import Store
from base_legal.wiring import make_retriever, open_store

ROOT = Path(__file__).parents[1]
OUT = ROOT / "reports" / "rerank"
MODELS = {
    "bge": "bge-reranker-v2-m3",
    "minilm": "mmarco-mminilmv2",
    "qwen": "qwen3-reranker-0.6b",
}
MAX_TOKENS = 512
QWEN_TASK = (
    "Given a question about Brazilian data protection or access-to-information law, "
    "judge whether the legal provision helps answer it"
)

Scorer = Callable[[str, Sequence[str]], list[float]]


def _local(name: str, settings: Settings) -> Path:
    lock = load_lock_file(ROOT / "benchmarks" / "models" / f"{name}.lock.json")
    directory = settings.models_dir / name
    with httpx.Client(timeout=httpx.Timeout(60, read=600)) as client:
        fetch_model(lock, directory, client)  # verifies every SHA-256
    return directory


def cross_encoder(path: Path) -> Scorer:
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(str(path), max_length=MAX_TOKENS, local_files_only=True)

    def score(question: str, documents: Sequence[str]) -> list[float]:
        return [float(s) for s in model.predict([(question, d) for d in documents])]

    return score


def qwen_reranker(path: Path) -> Scorer:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(path, padding_side="left", local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True).eval()
    yes, no = tokenizer.convert_tokens_to_ids("yes"), tokenizer.convert_tokens_to_ids("no")
    prefix = tokenizer.encode(
        "<|im_start|>system\nJudge whether the Document meets the requirements based on the "
        'Query and the Instruct provided. Note that the answer can only be "yes" or "no".'
        "<|im_end|>\n<|im_start|>user\n",
        add_special_tokens=False,
    )
    suffix = tokenizer.encode(
        "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n", add_special_tokens=False
    )

    def score(question: str, documents: Sequence[str]) -> list[float]:
        pairs = [
            f"<Instruct>: {QWEN_TASK}\n<Query>: {question}\n<Document>: {d}" for d in documents
        ]
        encoded = tokenizer(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=MAX_TOKENS - len(prefix) - len(suffix),
        )
        encoded["input_ids"] = [prefix + ids + suffix for ids in encoded["input_ids"]]
        batch = tokenizer.pad(encoded, padding=True, return_tensors="pt")
        with torch.inference_mode():
            logits = model(**batch).logits[:, -1, :]
        pair = torch.stack([logits[:, no], logits[:, yes]], dim=1)
        return torch.nn.functional.log_softmax(pair, dim=1)[:, 1].exp().tolist()  # type: ignore[no-any-return]

    return score


@dataclass
class Row:
    item: str
    split: str
    expected: tuple[str, ...]
    base: list[str]
    reranked: list[str]
    blended: list[str]
    best_score: float
    best_similarity: float | None
    seconds: float


def _contents(store: Store, ids: Sequence[str]) -> dict[str, str]:
    rows = store.conn.execute(
        "SELECT provision_id, content FROM chunks WHERE provision_id = ANY(%s)", (list(ids),)
    ).fetchall()
    return {str(r["provision_id"]): str(r["content"]) for r in rows}


def _rrf(*rankings: Sequence[str], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda pid: -scores[pid])


def rerank(
    result: SearchResult, contents: dict[str, str], question: str, scorer: Scorer
) -> tuple[list[str], list[str], float, float]:
    explicit = [h.provision.id for h in result.hits if h.explicit]
    rest = [h.provision.id for h in result.hits if not h.explicit and h.provision.id in contents]
    started = time.perf_counter()
    scores = scorer(question, [contents[pid] for pid in rest]) if rest else []
    seconds = time.perf_counter() - started
    by_score = [pid for _, pid in sorted(zip(scores, rest, strict=True), key=lambda x: -x[0])]
    return (
        explicit + by_score,
        explicit + _rrf(rest, by_score),
        max(scores, default=0.0),
        seconds,
    )


def _metrics(rows: list[Row], attr: str) -> dict[str, float]:
    recall5, rr = [], []
    for row in rows:
        ranking: list[str] = getattr(row, attr)
        recall5.append(len(set(row.expected) & set(ranking[:5])) / len(row.expected))
        first = next((i for i, pid in enumerate(ranking, 1) if pid in row.expected), None)
        rr.append(1.0 / first if first else 0.0)
    return {"recall_at_5": statistics.fmean(recall5), "mrr": statistics.fmean(rr)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth", type=int, default=20, help="hybrid candidates to rerank")
    parser.add_argument("--models", default="bge,minilm,qwen")
    args = parser.parse_args()
    settings = Settings()
    golden = GoldenSet.load(ROOT / "evals" / "golden.yaml")
    store = open_store(settings)
    retriever = make_retriever(settings, store)
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        candidates = []
        for item in golden.answerable:
            result = retriever.search(item.question, k=args.depth)
            candidates.append((item.id, item.split.value, item.expected, item.question, result))
        refusals = []
        for refuse in golden.refuse:
            if refuse.reason is RefuseReason.NONEXISTENT_PROVISION:
                continue  # refused by the explicit-reference check, not by a score
            result = retriever.search(refuse.question, k=args.depth)
            refusals.append((refuse.id, refuse.split.value, refuse.question, result))
        ids = {h.provision.id for *_, r in candidates + refusals for h in r.hits}
        contents = _contents(store, sorted(ids))
    finally:
        store.close()

    summary: dict[str, Any] = {"depth": args.depth}
    for key in args.models.split(","):
        name = MODELS[key]
        path = _local(name, settings)
        scorer = qwen_reranker(path) if key == "qwen" else cross_encoder(path)
        rows: list[Row] = []
        for item_id, split, expected, question, result in candidates:
            reranked, blended, best, seconds = rerank(result, contents, question, scorer)
            base = [h.provision.id for h in result.hits]
            rows.append(
                Row(
                    item_id,
                    split,
                    expected,
                    base,
                    reranked,
                    blended,
                    best,
                    result.best_similarity,
                    seconds,
                )
            )
        refused_best = []
        for refuse_id, split, question, result in refusals:
            _, _, best, _ = rerank(result, contents, question, scorer)
            refused_best.append(
                {
                    "id": refuse_id,
                    "split": split,
                    "best_score": best,
                    "best_similarity": result.best_similarity,
                }
            )
        report: dict[str, Any] = {"model": name}
        for split in (Split.DEV, Split.HOLDOUT, Split.ALL):
            subset = [r for r in rows if split is Split.ALL or r.split == split.value]
            report[split.value] = {
                attr: _metrics(subset, attr) for attr in ("base", "reranked", "blended")
            }
        latencies = sorted(r.seconds * 1000 for r in rows)
        report["rerank_ms_p50"] = statistics.median(latencies)
        report["rerank_ms_p95"] = latencies[int(0.95 * (len(latencies) - 1))]
        report["answerable_best_score_min"] = min(r.best_score for r in rows)
        report["answerable_best_score_p05"] = sorted(r.best_score for r in rows)[len(rows) // 20]
        report["refuse_best_scores"] = refused_best
        summary[key] = report
        print(json.dumps(report, indent=1, default=float))
        (OUT / f"{key}-rows.json").write_text(
            json.dumps([r.__dict__ for r in rows], indent=1, default=float), encoding="utf-8"
        )
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=float), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
