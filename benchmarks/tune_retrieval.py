"""Grid-search retrieval knobs on the golden **dev** split (never on holdout).

    DATABASE_URL=... uv run python benchmarks/tune_retrieval.py [--schema gate_b1]
    DATABASE_URL=... uv run python benchmarks/tune_retrieval.py --schema gate_b3 \
        --query-model qwen3-embedding-0.6b    # a benchmark-only model (embedding gate)

Query embeddings are computed once per question (local model) and cached, so
each combination only costs database queries. The best combination by dev
recall@5 (then MRR) is printed; confirm it on holdout with
``base-legal eval retrieval --split holdout`` before adopting it.
"""

from __future__ import annotations

import argparse
import itertools
from collections.abc import Sequence
from pathlib import Path

import httpx
import psycopg

from base_legal.config import Settings
from base_legal.embeddings.base import Embedder, Vectors
from base_legal.embeddings.factory import make_query_embedder
from base_legal.embeddings.model_store import fetch_model, load_lock_file
from base_legal.embeddings.providers import LocalSentenceTransformerEmbedder
from base_legal.evals.golden import GoldenSet, Split
from base_legal.evals.retrieval import evaluate
from base_legal.retrieval.search import Retriever, Tuning
from base_legal.store.db import Store

ROOT = Path(__file__).parents[1]


class CachedEmbedder:
    def __init__(self, inner: Embedder) -> None:
        self.inner = inner
        self.cache: dict[str, Vectors] = {}

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def family(self) -> str:
        return self.inner.family

    @property
    def dimension(self) -> int:
        return self.inner.dimension

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        return self.inner.embed_documents(texts)

    def embed_query(self, text: str) -> Vectors:
        if text not in self.cache:
            self.cache[text] = self.inner.embed_query(text)
        return self.cache[text]


def _query_embedder(settings: Settings, name: str | None) -> Embedder:
    if name is None:
        return make_query_embedder(settings)
    lock = load_lock_file(ROOT / "benchmarks" / "models" / f"{name}.lock.json")
    directory = settings.models_dir / name
    with httpx.Client(timeout=httpx.Timeout(60, read=600)) as client:
        fetch_model(lock, directory, client)  # verifies every SHA-256
    return LocalSentenceTransformerEmbedder(path=directory, model=name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", default="public")
    parser.add_argument(
        "--query-model",
        default=None,
        help="benchmark model in benchmarks/models (default: the shipped query embedder)",
    )
    args = parser.parse_args()
    settings = Settings()
    url = psycopg.conninfo.make_conninfo(
        settings.database_url, options=f"-c search_path={args.schema},public"
    )
    golden = GoldenSet.load(ROOT / "evals" / "golden.yaml")
    embedder = CachedEmbedder(_query_embedder(settings, args.query_model))
    store = Store.connect(url)
    results = []
    try:
        grid = itertools.product((0, 1, 2, 4, 32), (1.0, 0.5, 1.5), (0.0, 0.2, 0.35, 0.5))
        for normalization, lexical_weight, parent_weight in grid:
            tuning = Tuning(
                fts_normalization=normalization,
                lexical_weight=lexical_weight,
                parent_weight=parent_weight,
            )
            retriever = Retriever(store, embedder, tuning=tuning)
            m = evaluate(retriever, golden, split=Split.DEV, threshold=None, label="tune").metrics
            results.append((m.recall_at_5, m.mrr, m.recall_at_10, tuning))
            print(f"{tuning}  R@5={m.recall_at_5:.3f} MRR={m.mrr:.3f} R@10={m.recall_at_10:.3f}")
    finally:
        store.close()
    results.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
    print("\nTop 5 on dev:")
    for r5, mrr, r10, tuning in results[:5]:
        print(f"  {tuning}  R@5={r5:.3f} MRR={mrr:.3f} R@10={r10:.3f}")


if __name__ == "__main__":
    main()
