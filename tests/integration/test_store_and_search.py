import os
from pathlib import Path

import pytest

from base_legal.chunking.chunker import chunk_document
from base_legal.config import IngestMode
from base_legal.corpus.manifest import Manifest
from base_legal.corpus.models import Document
from base_legal.embeddings.base import IncompatibleEmbedderError, check_compatible
from base_legal.embeddings.precomputed import (
    PrecomputedMismatchError,
    artifact_filename,
    save_vectors,
)
from base_legal.embeddings.providers import HashingEmbedder
from base_legal.ingest import ingest_documents
from base_legal.retrieval.search import Retriever
from base_legal.store.db import IndexMismatchError, Store

pytestmark = pytest.mark.integration


def _ingest(store: Store, document: Document, manifest: Manifest, tmp_path: Path) -> None:
    ingest_documents(
        store,
        [document],
        manifest,
        embeddings_dir=tmp_path,
        mode=IngestMode.LOCAL,
        precomputed_model="voyage-4-large",
        document_embedder=HashingEmbedder(),
    )


def test_ingest_is_idempotent(
    store: Store, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    kwargs = {
        "embeddings_dir": tmp_path,
        "mode": IngestMode.LOCAL,
        "precomputed_model": "voyage-4-large",
        "document_embedder": HashingEmbedder(),
    }
    (first,) = ingest_documents(store, [document], manifest, **kwargs)  # type: ignore[arg-type]
    (second,) = ingest_documents(store, [document], manifest, **kwargs)  # type: ignore[arg-type]
    assert not first.skipped
    assert second.skipped
    assert store.count_chunks() == first.chunks == len(document.in_force())
    assert store.get_meta() == {"embedding_family": "test-hashing", "embedding_dim": "1024"}


def test_provisions_round_trip(
    store: Store, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    _ingest(store, document, manifest, tmp_path)
    stored = store.provisions(["lgpd:art65:incI-A", "lgpd:art7:par1", "lgpd:nope"])
    assert set(stored) == {"lgpd:art65:incI-A", "lgpd:art7:par1"}
    assert stored["lgpd:art65:incI-A"] == document.by_id()["lgpd:art65:incI-A"]
    assert stored["lgpd:art7:par1"].revoked


def test_lexical_search_is_accent_insensitive(
    store: Store, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    _ingest(store, document, manifest, tmp_path)
    hits = [r.provision_id for r in store.lexical("prevencao a fraude", 5)]
    assert hits[0] == "lgpd:art11:incII:alig"
    assert store.lexical("!!! ???", 5) == []


def test_lexical_search_resists_tsquery_injection(
    store: Store, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    _ingest(store, document, manifest, tmp_path)
    # Operators and quotes are stripped; this must not raise a syntax error.
    assert isinstance(store.lexical("fraude') & !(x | :* <-> '", 5), list)


def test_hybrid_search_puts_explicit_references_first(
    store: Store, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    _ingest(store, document, manifest, tmp_path)
    retriever = Retriever(store, HashingEmbedder())
    result = retriever.search("O que diz o art. 7º, IX, sobre interesses legítimos?", k=5)
    assert result.hits[0].provision.id == "lgpd:art7:incIX"
    assert result.hits[0].explicit
    assert len({h.provision.id for h in result.hits}) == len(result.hits)
    assert result.best_similarity is not None


def test_missing_reference_is_reported(
    store: Store, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    _ingest(store, document, manifest, tmp_path)
    result = Retriever(store, HashingEmbedder()).search("O que diz o art. 99 da LGPD?")
    assert result.missing_references == ("lgpd:art99",)
    assert all(not h.explicit for h in result.hits)


def test_space_guard(store: Store, document: Document, manifest: Manifest, tmp_path: Path) -> None:
    _ingest(store, document, manifest, tmp_path)
    with pytest.raises(IndexMismatchError):
        store.ensure_space("voyage-4", 1024)
    with pytest.raises(IncompatibleEmbedderError):
        check_compatible("voyage-4", 1024, HashingEmbedder())


def test_precomputed_mode(
    store: Store, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    chunks = chunk_document(document, "LGPD")
    vectors = HashingEmbedder(family="voyage-4").embed_documents([c.content for c in chunks])
    name = artifact_filename("lgpd", "voyage-4-large", 1024)
    artifact = save_vectors(
        tmp_path / name,
        [c.provision_id for c in reversed(chunks)],
        vectors[::-1],
        model="voyage-4-large",
        corpus_sha256=document.source_sha256,
    )
    manifest.documents[0].embeddings = [artifact]

    (report,) = ingest_documents(
        store,
        [document],
        manifest,
        embeddings_dir=tmp_path,
        mode=IngestMode.PRECOMPUTED,
        precomputed_model="voyage-4-large",
        document_embedder=None,
    )
    assert report.precomputed
    assert store.get_meta()["embedding_family"] == "voyage-4"
    # Order in the file does not matter: vectors are matched by provision id.
    query = HashingEmbedder(family="voyage-4").embed_query(chunks[3].content)
    assert store.dense(query, 1)[0].provision_id == chunks[3].provision_id


def test_precomputed_tampering_is_rejected(
    store: Store, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    chunks = chunk_document(document, "LGPD")
    vectors = HashingEmbedder().embed_documents([c.content for c in chunks])
    path = tmp_path / artifact_filename("lgpd", "voyage-4-large", 1024)
    artifact = save_vectors(
        path,
        [c.provision_id for c in chunks],
        vectors,
        model="voyage-4-large",
        corpus_sha256=document.source_sha256,
    )
    manifest.documents[0].embeddings = [artifact]
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(PrecomputedMismatchError, match="hash"):
        ingest_documents(
            store,
            [document],
            manifest,
            embeddings_dir=tmp_path,
            mode=IngestMode.PRECOMPUTED,
            precomputed_model="voyage-4-large",
            document_embedder=None,
        )


def test_ingest_is_committed_and_visible_to_other_connections(
    store: Store, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    # Regression: reads used to open an implicit transaction, turning the ingest
    # into a savepoint that was rolled back on close.
    store.get_meta()
    _ingest(store, document, manifest, tmp_path)
    store.close()
    other = Store.connect(os.environ["DATABASE_URL"])
    try:
        assert other.count_chunks() == len(document.in_force())
    finally:
        other.close()
