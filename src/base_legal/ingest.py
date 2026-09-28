"""Ingestion: corpus JSON + document vectors -> PostgreSQL (ADR 0003 modes)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from base_legal.chunking.chunker import Chunk, chunk_document
from base_legal.config import IngestMode
from base_legal.corpus.history import DocumentHistory
from base_legal.corpus.manifest import Manifest
from base_legal.corpus.models import Document
from base_legal.embeddings.base import Embedder, Vectors, model_family
from base_legal.embeddings.precomputed import (
    PrecomputedMismatchError,
    load_vectors,
    local_artifact,
)
from base_legal.store.db import Store

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestReport:
    document_id: str
    chunks: int
    embedding_model: str
    precomputed: bool
    skipped: bool


def _load_precomputed(
    document: Document, manifest: Manifest, embeddings_dir: Path, model: str, chunks: list[Chunk]
) -> Vectors | None:
    recorded = [a for a in manifest.get(document.id).embeddings if a.model == model]
    artifact = recorded[0] if recorded else local_artifact(embeddings_dir, document.id, model)
    if artifact is None:
        return None
    if not recorded:
        log.info("%s: using locally generated %s vectors (not in the manifest)", document.id, model)
    return load_vectors(
        embeddings_dir,
        artifact,
        corpus_sha256=document.source_sha256,
        expected_ids=[c.provision_id for c in chunks],
    )


def _load_history(
    store: Store, document: Document, histories: Mapping[str, DocumentHistory] | None
) -> None:
    history = (histories or {}).get(document.id)
    if history is None:
        return
    if history.source_sha256 != document.source_sha256:
        log.warning("%s: history is stale (different source hash); not loaded", document.id)
        return
    store.replace_versions(history)


def ingest_documents(
    store: Store,
    documents: list[Document],
    manifest: Manifest,
    *,
    embeddings_dir: Path,
    mode: IngestMode,
    precomputed_model: str,
    document_embedder: Embedder | None,
    histories: Mapping[str, DocumentHistory] | None = None,
) -> list[IngestReport]:
    """Ingest each document once per (source hash, embedding model).

    * ``precomputed``: vectors from ``embeddings_dir`` or fail.
    * ``api`` / ``local``: always embed with ``document_embedder``.
    * ``auto``: precomputed when valid, else ``document_embedder``.

    Earlier wordings (``histories``, ADR 0014) are reloaded every time: they are
    cheap and may be added after a document was first ingested.
    """
    reports: list[IngestReport] = []
    for document in documents:
        chunks = chunk_document(document, manifest.get(document.id).short_name)

        vectors: Vectors | None = None
        if mode in (IngestMode.AUTO, IngestMode.PRECOMPUTED):
            try:
                vectors = _load_precomputed(
                    document, manifest, embeddings_dir, precomputed_model, chunks
                )
            except PrecomputedMismatchError:
                if mode is IngestMode.PRECOMPUTED:
                    raise
                log.warning("precomputed vectors for %s unusable; re-embedding", document.id)
            if vectors is None and mode is IngestMode.PRECOMPUTED:
                raise PrecomputedMismatchError(
                    f"no precomputed {precomputed_model} vectors for {document.id}"
                )

        if vectors is not None:
            model = precomputed_model
        elif document_embedder is not None:
            model = document_embedder.model
        else:
            raise RuntimeError(f"{document.id}: no precomputed vectors and no document embedder")

        if store.is_current(document, model):
            _load_history(store, document, histories)
            reports.append(IngestReport(document.id, len(chunks), model, vectors is not None, True))
            continue
        precomputed = vectors is not None
        if vectors is None and document_embedder is not None:
            vectors = document_embedder.embed_documents([c.content for c in chunks])
        if vectors is None:  # pragma: no cover - unreachable, keeps the type checker honest
            raise RuntimeError("no vectors")
        store.ensure_space(model_family(model), int(vectors.shape[1]))
        store.replace_document(document, chunks, vectors, model)
        _load_history(store, document, histories)
        reports.append(IngestReport(document.id, len(chunks), model, precomputed, False))
    return reports
