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
from base_legal.embeddings.precomputed import (
    PrecomputedMismatchError,
    artifact_filename,
    load_vectors,
    local_artifact,
    save_vectors,
    write_sidecar,
)
from base_legal.embeddings.providers import (
    HashingEmbedder,
    LocalSentenceTransformerEmbedder,
    VoyageApiEmbedder,
    token_batches,
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


def test_token_batches_respect_the_token_budget() -> None:
    texts = ["x" * 2999, "y" * 2999, "z" * 2999, "w"]  # ~1000 tokens each
    batches = list(token_batches(texts, max_items=64, max_tokens=2000))
    assert [len(b) for b in batches] == [2, 2]
    assert [t for b in batches for t in b] == texts
    # A single text above the budget still goes out alone rather than being dropped.
    assert list(token_batches(["x" * 9000], max_tokens=10)) == [["x" * 9000]]


class RateLimitError(Exception):
    """Same class name as ``voyageai.error.RateLimitError``."""


class _FlakyVoyage(_FakeVoyage):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    def embed(self, texts: list[str], **kwargs: Any) -> _Result:
        if self.failures:
            self.failures -= 1
            raise RateLimitError("3 RPM")
        return super().embed(texts, **kwargs)


def test_voyage_retries_on_rate_limit_with_backoff() -> None:
    waits: list[float] = []
    client = _FlakyVoyage(failures=2)
    embedder = VoyageApiEmbedder(
        api_key="unused", client=client, retry_seconds=10, sleep=waits.append
    )
    assert embedder.embed_documents(["a", "b"]).shape == (2, EMBEDDING_DIM)
    assert waits == [10, 20]


def test_voyage_gives_up_after_max_retries_and_never_retries_other_errors() -> None:
    embedder = VoyageApiEmbedder(
        api_key="unused", client=_FlakyVoyage(failures=5), max_retries=2, sleep=lambda _: None
    )
    with pytest.raises(RateLimitError):
        embedder.embed_documents(["a"])

    class _Broken(_FakeVoyage):
        def embed(self, texts: list[str], **kwargs: Any) -> _Result:
            raise ValueError("bad request")

    waits: list[float] = []
    broken = VoyageApiEmbedder(api_key="unused", client=_Broken(), sleep=waits.append)
    with pytest.raises(ValueError, match="bad request"):
        broken.embed_documents(["a"])
    assert waits == []


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


def test_unrecorded_vectors_are_found_through_their_sidecar(tmp_path: Path) -> None:
    vectors = HashingEmbedder().embed_documents(["a", "b"])
    artifact = save_vectors(
        tmp_path / artifact_filename("lgpd", "voyage-4-large", EMBEDDING_DIM),
        ["p1", "p2"],
        vectors,
        model="voyage-4-large",
        corpus_sha256="b" * 64,
    )
    assert local_artifact(tmp_path, "lgpd", "voyage-4-large") is None
    write_sidecar(tmp_path, artifact)
    assert local_artifact(tmp_path, "lgpd", "voyage-4-large") == artifact
    assert local_artifact(tmp_path, "lgpd", "voyage-4-nano") is None
    assert local_artifact(tmp_path, "res-anpd-1-2021", "voyage-4-large") is None
