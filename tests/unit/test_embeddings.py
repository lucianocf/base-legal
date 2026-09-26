from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from base_legal.embeddings.base import (
    EMBEDDING_DIM,
    IncompatibleEmbedderError,
    check_compatible,
    l2_normalize,
    model_family,
)
from base_legal.embeddings.precomputed import PrecomputedMismatchError, load_vectors, save_vectors
from base_legal.embeddings.providers import (
    HashingEmbedder,
    LocalSentenceTransformerEmbedder,
    VoyageApiEmbedder,
)


@dataclass
class _Result:
    embeddings: list[list[float]]


class _FakeVoyage:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def embed(self, texts: list[str], **kwargs: Any) -> _Result:
        self.calls.append({"n": len(texts), **kwargs})
        return _Result([[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts])


class _FakeSentenceTransformer:
    def __init__(self) -> None:
        self.kinds: list[str] = []

    def encode_query(self, texts: list[str], **_: Any) -> np.ndarray:
        self.kinds.append("query")
        return np.ones((len(texts), 2048), dtype=np.float32)

    def encode_document(self, texts: list[str], **_: Any) -> np.ndarray:
        self.kinds.append("document")
        return np.ones((len(texts), 2048), dtype=np.float32)


def test_model_family() -> None:
    assert model_family("voyage-4-large") == model_family("voyage-4-nano") == "voyage-4"
    assert model_family("qwen3-embedding-0.6b") == "qwen3-embedding-0.6b"


def test_voyage_embeds_documents_in_batches() -> None:
    client = _FakeVoyage()
    embedder = VoyageApiEmbedder(api_key="unused", client=client)
    vectors = embedder.embed_documents([f"t{i}" for i in range(130)])
    assert vectors.shape == (130, EMBEDDING_DIM)
    assert [c["n"] for c in client.calls] == [64, 64, 2]
    assert {c["input_type"] for c in client.calls} == {"document"}
    assert {c["output_dimension"] for c in client.calls} == {EMBEDDING_DIM}
    assert embedder.embed_documents([]).shape == (0, EMBEDDING_DIM)


def test_voyage_refuses_to_embed_questions() -> None:
    embedder = VoyageApiEmbedder(api_key="unused", client=_FakeVoyage())
    with pytest.raises(RuntimeError, match="embedded locally"):
        embedder.embed_query("Meu CPF vazou?")


def test_local_embedder_uses_query_and_document_prompts_and_truncates() -> None:
    backend = _FakeSentenceTransformer()
    embedder = LocalSentenceTransformerEmbedder(
        path=Path("unused"), model="voyage-4-nano", backend=backend
    )
    query = embedder.embed_query("pergunta")
    docs = embedder.embed_documents(["a", "b"])
    assert query.shape == (EMBEDDING_DIM,)
    assert docs.shape == (2, EMBEDDING_DIM)
    assert np.allclose(np.linalg.norm(docs, axis=1), 1.0)
    assert backend.kinds == ["query", "document"]
    assert embedder.family == "voyage-4"


def test_hashing_embedder_is_deterministic() -> None:
    a = HashingEmbedder().embed_query("dados pessoais sensíveis")
    b = HashingEmbedder().embed_query("dados pessoais sensíveis")
    assert np.array_equal(a, b)
    assert np.isclose(np.linalg.norm(a), 1.0)


def test_compatibility_guard() -> None:
    check_compatible("test-hashing", EMBEDDING_DIM, HashingEmbedder())
    with pytest.raises(IncompatibleEmbedderError):
        check_compatible("voyage-4", EMBEDDING_DIM, HashingEmbedder())


def test_l2_normalize_handles_zero_vectors() -> None:
    out = l2_normalize(np.zeros((2, 3), dtype=np.float32))
    assert not np.isnan(out).any()


def test_precomputed_round_trip_and_checks(tmp_path: Path) -> None:
    vectors = HashingEmbedder().embed_documents(["a", "b", "c"])
    artifact = save_vectors(
        tmp_path / "x.npz", ["p1", "p2", "p3"], vectors, model="m", corpus_sha256="b" * 64
    )
    loaded = load_vectors(
        tmp_path, artifact, corpus_sha256="b" * 64, expected_ids=["p3", "p1", "p2"]
    )
    assert np.array_equal(loaded, vectors[[2, 0, 1]])

    with pytest.raises(PrecomputedMismatchError, match="another corpus"):
        load_vectors(tmp_path, artifact, corpus_sha256="c" * 64, expected_ids=["p1", "p2", "p3"])
    with pytest.raises(PrecomputedMismatchError, match="ids differ"):
        load_vectors(tmp_path, artifact, corpus_sha256="b" * 64, expected_ids=["p1"])
    with pytest.raises(ValueError, match="length"):
        save_vectors(tmp_path / "y.npz", ["p1"], vectors, model="m", corpus_sha256="b" * 64)
