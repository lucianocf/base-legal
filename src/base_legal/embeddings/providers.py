"""Embedder implementations.

* :class:`VoyageApiEmbedder` — documents (public law text) via the Voyage API.
* :class:`LocalSentenceTransformerEmbedder` — questions, in-process, with
  open weights (``voyage-4-nano``); questions never leave the machine.
* :class:`HashingEmbedder` — deterministic, dependency-free; tests only.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from base_legal.embeddings.base import EMBEDDING_DIM, Vectors, l2_normalize, model_family

VOYAGE_BATCH_SIZE = 64


class VoyageApiEmbedder:
    """Embed **public legal text only**. Never pass user questions here (ADR 0003)."""

    def __init__(
        self, api_key: str, model: str = "voyage-4-large", client: Any | None = None
    ) -> None:
        if client is None:
            import voyageai  # optional dependency: `uv sync --extra voyage`

            client = voyageai.Client(api_key=api_key)
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def family(self) -> str:
        return model_family(self._model)

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        batches: list[Vectors] = []
        for start in range(0, len(texts), VOYAGE_BATCH_SIZE):
            batch = list(texts[start : start + VOYAGE_BATCH_SIZE])
            result = self._client.embed(
                batch, model=self._model, input_type="document", output_dimension=EMBEDDING_DIM
            )
            batches.append(np.asarray(result.embeddings, dtype=np.float32))
        if not batches:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        return l2_normalize(np.vstack(batches))

    def embed_query(self, text: str) -> Vectors:
        raise RuntimeError(
            "questions are embedded locally; the Voyage API is for public law text only"
        )


class LocalSentenceTransformerEmbedder:
    """Local open-weight embedder, pinned by revision; no remote code by default."""

    def __init__(
        self,
        path: Path,
        model: str,
        *,
        trust_remote_code: bool = False,
        backend: Any | None = None,
    ) -> None:
        """Load from a local, hash-verified directory (see ``model_store``); never from the Hub."""
        if backend is None:
            from sentence_transformers import SentenceTransformer  # optional: `--extra local`

            backend = SentenceTransformer(
                str(path),
                trust_remote_code=trust_remote_code,
                local_files_only=True,
                truncate_dim=EMBEDDING_DIM,
                device="cpu",
            )
        self._backend = backend
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def family(self) -> str:
        return model_family(self._model)

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def _encode(self, texts: list[str], kind: str) -> Vectors:
        encode = getattr(self._backend, f"encode_{kind}", None) or self._backend.encode
        vectors = np.asarray(encode(texts, normalize_embeddings=True), dtype=np.float32)
        return l2_normalize(vectors.reshape(len(texts), -1)[:, :EMBEDDING_DIM])

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        return self._encode(list(texts), "document")

    def embed_query(self, text: str) -> Vectors:
        return np.asarray(self._encode([text], "query")[0], dtype=np.float32)


class HashingEmbedder:
    """Bag-of-words feature hashing. Deterministic and offline; for tests only."""

    def __init__(self, dimension: int = EMBEDDING_DIM, family: str = "test-hashing") -> None:
        self._dimension = dimension
        self._family = family

    @property
    def model(self) -> str:
        return "test-hashing"

    @property
    def family(self) -> str:
        return self._family

    @property
    def dimension(self) -> int:
        return self._dimension

    def _vector(self, text: str) -> Vectors:
        vector = np.zeros(self._dimension, dtype=np.float32)
        for token in re.findall(r"\w+", text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            vector[int.from_bytes(digest, "big") % self._dimension] += 1.0
        return vector

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        if not texts:
            return np.zeros((0, self._dimension), dtype=np.float32)
        return l2_normalize(np.vstack([self._vector(t) for t in texts]))

    def embed_query(self, text: str) -> Vectors:
        return np.asarray(l2_normalize(self._vector(text)[None, :])[0], dtype=np.float32)
