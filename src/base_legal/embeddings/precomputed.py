"""Precomputed document vectors, committed under ``corpus/embeddings/`` (ADR 0003).

Stored as ``.npz`` (``ids`` + ``vectors``), loaded with ``allow_pickle=False``
and verified against the SHA-256 recorded in the manifest before use.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from base_legal.corpus.manifest import EmbeddingArtifact, sha256_hex
from base_legal.embeddings.base import Vectors


class PrecomputedMismatchError(RuntimeError):
    """Precomputed vectors are missing, tampered with, or stale."""


def artifact_filename(doc_id: str, model: str, dimension: int) -> str:
    return f"{doc_id}.{model}.{dimension}.npz"


def save_vectors(
    path: Path,
    ids: Sequence[str],
    vectors: Vectors,
    *,
    model: str,
    corpus_sha256: str,
) -> EmbeddingArtifact:
    if vectors.shape[0] != len(ids):
        raise ValueError("ids and vectors differ in length")
    buffer = io.BytesIO()
    np.savez_compressed(buffer, ids=np.asarray(ids, dtype=str), vectors=vectors.astype(np.float32))
    data = buffer.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return EmbeddingArtifact(
        model=model,
        dimension=int(vectors.shape[1]),
        file=path.name,
        sha256=sha256_hex(data),
        corpus_sha256=corpus_sha256,
    )


def load_vectors(
    embeddings_dir: Path,
    artifact: EmbeddingArtifact,
    *,
    corpus_sha256: str,
    expected_ids: Sequence[str],
) -> Vectors:
    """Load vectors in ``expected_ids`` order, verifying integrity and freshness."""
    path = embeddings_dir / artifact.file
    if not path.exists():
        raise PrecomputedMismatchError(f"missing {path}")
    data = path.read_bytes()
    if sha256_hex(data) != artifact.sha256:
        raise PrecomputedMismatchError(f"{path.name}: hash does not match the manifest")
    if artifact.corpus_sha256 != corpus_sha256:
        raise PrecomputedMismatchError(f"{path.name}: computed from another corpus snapshot")
    with np.load(io.BytesIO(data), allow_pickle=False) as archive:
        ids = [str(i) for i in archive["ids"]]
        vectors = np.asarray(archive["vectors"], dtype=np.float32)
    if sorted(ids) != sorted(expected_ids):
        raise PrecomputedMismatchError(f"{path.name}: provision ids differ from the corpus")
    position = {pid: n for n, pid in enumerate(ids)}
    return vectors[[position[pid] for pid in expected_ids]]
