"""Embedding validation gate (ADR 0003): B0-B4, dense-only and hybrid.

Maintainer-only benchmark. Each configuration is ingested into its own
PostgreSQL schema of ``DATABASE_URL`` and evaluated with the golden set on
the dev and holdout splits. Questions are always embedded locally; Voyage
only ever saw public law text (``corpus embed``, ADR 0009 vectors kept
local). Qwen3 and BGE-M3 are pinned in ``benchmarks/models`` and are never
production dependencies.

    uv sync --extra local --extra bench
    uv run python benchmarks/embedding_gate.py --configs B0,B1,B2,B3,B4
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
import psycopg

from base_legal.config import IngestMode, Settings
from base_legal.corpus.manifest import Manifest
from base_legal.corpus.pipeline import load_documents
from base_legal.embeddings.base import Embedder
from base_legal.embeddings.factory import make_query_embedder
from base_legal.embeddings.model_store import fetch_model, load_lock_file
from base_legal.embeddings.providers import LocalSentenceTransformerEmbedder
from base_legal.evals.golden import GoldenSet, Split
from base_legal.evals.retrieval import RetrievalReport, evaluate
from base_legal.ingest import ingest_documents
from base_legal.retrieval.search import Retriever, SearchMode
from base_legal.store.db import Store

ROOT = Path(__file__).parents[1]
OUT = ROOT / "reports" / "gate"


@dataclass(frozen=True)
class Config:
    name: str
    documents: str
    queries: str
    schema: str
    modes: tuple[SearchMode, ...]


CONFIGS = {
    "B0": Config("B0", "none (full-text only)", "none", "gate_b2", (SearchMode.LEXICAL,)),
    "B1": Config(
        "B1",
        "voyage-4-large (API)",
        "voyage-4-nano (local)",
        "gate_b1",
        (SearchMode.DENSE, SearchMode.HYBRID),
    ),
    "B2": Config(
        "B2",
        "voyage-4-nano (local)",
        "voyage-4-nano (local)",
        "gate_b2",
        (SearchMode.DENSE, SearchMode.HYBRID),
    ),
    "B3": Config(
        "B3",
        "Qwen3-Embedding-0.6B",
        "Qwen3-Embedding-0.6B",
        "gate_b3",
        (SearchMode.DENSE, SearchMode.HYBRID),
    ),
    "B4": Config(
        "B4", "BGE-M3 (dense)", "BGE-M3 (dense)", "gate_b4", (SearchMode.DENSE, SearchMode.HYBRID)
    ),
}
BENCH_MODELS = {"B3": "qwen3-embedding-0.6b", "B4": "bge-m3"}


def _benchmark_embedder(name: str, settings: Settings) -> Embedder:
    lock = load_lock_file(ROOT / "benchmarks" / "models" / f"{name}.lock.json")
    directory = settings.models_dir / name
    with httpx.Client(timeout=httpx.Timeout(60, read=600)) as client:
        fetch_model(lock, directory, client)  # verifies every SHA-256
    return LocalSentenceTransformerEmbedder(path=directory, model=name)


def _schema_url(url: str, schema: str) -> str:
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}".encode())
    return psycopg.conninfo.make_conninfo(url, options=f"-c search_path={schema},public")


def run(
    config: Config, settings: Settings, golden: GoldenSet, ingest: bool
) -> list[RetrievalReport]:
    nano = make_query_embedder(settings)
    if config.name in BENCH_MODELS:
        query_embedder: Embedder = _benchmark_embedder(BENCH_MODELS[config.name], settings)
        document_embedder: Embedder | None = query_embedder
    elif config.name == "B1":
        query_embedder, document_embedder = nano, None  # documents: local voyage-4-large vectors
    else:
        query_embedder = document_embedder = nano

    store = Store.connect(_schema_url(settings.database_url, config.schema))
    try:
        if ingest and config.name != "B0":
            store.init_schema()
            manifest = Manifest.load(settings.corpus_dir / "manifest.yaml")
            ingest_documents(
                store,
                load_documents(settings.corpus_dir, manifest),
                manifest,
                embeddings_dir=settings.corpus_dir / "embeddings",
                mode=IngestMode.PRECOMPUTED if config.name == "B1" else IngestMode.LOCAL,
                precomputed_model="voyage-4-large",
                document_embedder=document_embedder,
            )
        reports = []
        for mode in config.modes:
            retriever = Retriever(
                store,
                None if mode is SearchMode.LEXICAL else query_embedder,
                candidate_pool=settings.candidate_pool,
                mode=mode,
                tuning=settings.tuning(),  # the shipped retrieval knobs
            )
            for split in (Split.DEV, Split.HOLDOUT, Split.ALL):
                label = f"{config.name}-{mode.value}"
                report = evaluate(
                    retriever,
                    golden,
                    split=split,
                    threshold=None,
                    label=label,
                    config={
                        "documents": config.documents,
                        "queries": config.queries,
                        "mode": mode.value,
                        **{k: str(v) for k, v in dataclasses.asdict(settings.tuning()).items()},
                    },
                )
                reports.append(report)
                m = report.metrics
                print(
                    f"{label:<12} {split.value:<8} R@5={m.recall_at_5:.3f} MRR={m.mrr:.3f} "
                    f"p50={m.latency_p50_ms:.0f}ms"
                )
        return reports
    finally:
        store.close()


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", default="B0,B1,B2,B3,B4")
    parser.add_argument("--no-ingest", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    golden = GoldenSet.load(ROOT / "evals" / "golden.yaml")
    OUT.mkdir(parents=True, exist_ok=True)
    for name in args.configs.split(","):
        reports = run(CONFIGS[name], settings, golden, ingest=not args.no_ingest)
        (OUT / f"{name}.json").write_text(
            json.dumps([r.model_dump(mode="json") for r in reports], indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
