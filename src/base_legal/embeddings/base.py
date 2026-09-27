"""Embedder protocol and shared-space compatibility guard (ADR 0003)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt

EMBEDDING_DIM = 1024

Vectors = npt.NDArray[np.float32]


@runtime_checkable
class Embedder(Protocol):
    @property
    def model(self) -> str:
        """Model name, e.g. ``voyage-4-nano``."""
        ...

    @property
    def family(self) -> str:
        """Embedding space shared by compatible models, e.g. ``voyage-4``."""
        ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> Vectors: ...

    def embed_query(self, text: str) -> Vectors: ...


class IncompatibleEmbedderError(RuntimeError):
    """The query embedder does not share the index's embedding space."""


def model_family(model: str) -> str:
    """``voyage-4-large`` / ``voyage-4-nano`` -> ``voyage-4``; other names map to themselves."""
    if model.startswith("voyage-4"):
        return "voyage-4"
    return model


def check_compatible(index_family: str, index_dimension: int, embedder: Embedder) -> None:
    if embedder.family != index_family or embedder.dimension != index_dimension:
        raise IncompatibleEmbedderError(
            f"index was built in space {index_family}/{index_dimension}; "
            f"query embedder {embedder.model} is {embedder.family}/{embedder.dimension}"
        )


def l2_normalize(vectors: Vectors) -> Vectors:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vectors / norms).astype(np.float32)
