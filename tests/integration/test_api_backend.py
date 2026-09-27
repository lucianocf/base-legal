from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic
import psycopg
import pytest
from fastapi.testclient import TestClient

from base_legal.api.app import create_app
from base_legal.chunking.chunker import chunk_document
from base_legal.config import IngestMode, Settings
from base_legal.corpus.manifest import Manifest
from base_legal.corpus.models import Document, DocumentKind, Provision, ProvisionKind
from base_legal.embeddings.providers import HashingEmbedder
from base_legal.ingest import ingest_documents
from base_legal.store.db import Store
from base_legal.wiring import DatabaseBackend

pytestmark = pytest.mark.integration


class _Echo:
    def __init__(self) -> None:
        self.messages = self

    def create(self, **kwargs: Any) -> anthropic.types.Message:
        first = kwargs["messages"][0]["content"][0]
        text = first["source"]["content"][0]["text"]
        return anthropic.types.Message.model_validate(
            {
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": kwargs["model"],
                "content": [
                    {
                        "type": "text",
                        "text": text,
                        "citations": [
                            {
                                "type": "content_block_location",
                                "cited_text": text,
                                "document_index": 0,
                                "document_title": "t",
                                "start_block_index": 0,
                                "end_block_index": 1,
                            }
                        ],
                    }
                ],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )


def test_database_backend_behind_the_api(
    store: Store,
    database_url: str,
    document: Document,
    manifest: Manifest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ingest_documents(
        store,
        [document],
        manifest,
        embeddings_dir=tmp_path,
        mode=IngestMode.LOCAL,
        precomputed_model="voyage-4-large",
        document_embedder=HashingEmbedder(),
    )
    monkeypatch.setattr(anthropic, "Anthropic", _Echo)
    settings = Settings(database_url=database_url, query_embedder="test-hashing")
    backend = DatabaseBackend(settings)
    try:
        client = TestClient(create_app(backend, settings))
        health = client.get("/health").json()
        assert health["index"]["embedding_family"] == "test-hashing"
        assert int(health["index"]["provisions_indexed"]) == len(document.in_force())

        answer = client.post("/ask", json={"question": "O que diz o art. 7º, IX?"}).json()
        assert answer["status"] == "answered"
        assert answer["provisions"][0]["id"] == "lgpd:art7:incIX"

        search = client.post("/search", json={"question": "art. 99", "k": 3}).json()
        assert search["missing_references"] == ["lgpd:art99"]
        assert search["refusal"] == "nonexistent_provision"

        assert client.get("/provisions/lgpd:art65:incI-A").status_code == 200
        assert client.get("/provisions/lgpd:art7:incXII").status_code == 404
    finally:
        backend.close()

    no_generation = DatabaseBackend(settings, with_generation=False)
    try:
        response = TestClient(create_app(no_generation, settings)).post(
            "/ask", json={"question": "O que diz o art. 7º, IX?"}
        )
        assert response.status_code == 503
    finally:
        no_generation.close()


def test_backend_starts_on_a_fresh_database(
    database_url: str,
    drop_tables: Callable[[psycopg.Connection[Any]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: `serve` crashed with "relation index_meta does not exist" when
    # started before the first `ingest` (the README quickstart order).
    with psycopg.connect(database_url, autocommit=True) as conn:
        drop_tables(conn)
    monkeypatch.setattr(anthropic, "Anthropic", _Echo)
    settings = Settings(database_url=database_url, query_embedder="test-hashing")
    backend = DatabaseBackend(settings)
    try:
        client = TestClient(create_app(backend, settings))
        assert client.get("/health").json()["index"]["provisions_indexed"] == "0"
        answer = client.post("/ask", json={"question": "O que é dado pessoal?"}).json()
        assert answer["status"] == "refused"
    finally:
        backend.close()


def test_cross_references_resolve_against_the_index(
    store: Store,
    database_url: str,
    document: Document,
    manifest: Manifest,
    tmp_path: Path,
) -> None:
    ingest_documents(
        store,
        [document],
        manifest,
        embeddings_dir=tmp_path,
        mode=IngestMode.LOCAL,
        precomputed_model="voyage-4-large",
        document_embedder=HashingEmbedder(),
    )
    assert store.annex_titles() == []
    assert store.normative_ids(["lgpd:art55A", "lgpd:art52", "lgpd:art65:incI"]) == {
        "lgpd:art55A",
        "lgpd:art65:incI",
    }
    settings = Settings(database_url=database_url, query_embedder="test-hashing")
    backend = DatabaseBackend(settings, with_generation=False)
    try:
        inciso = document.by_id()["lgpd:art65:incI"]
        [link] = backend.references({inciso.id: inciso.text})[inciso.id]
    finally:
        backend.close()
    # "arts. 55-A, 55-B e 55-C": only art. 55-A is in this fixture
    assert link.target == "lgpd:art55A"
    assert inciso.text[link.start : link.end] == "arts. 55-A"


def test_annex_titles_name_each_regulation(store: Store) -> None:
    title = "Anexo — REGULAMENTO DE TESTE SINTÉTICO"
    article = Provision(
        id="res-anpd-9-2099:anx1:art1",
        document_id="res-anpd-9-2099",
        parent_id=None,
        kind=ProvisionKind.ARTICLE,
        label="Art. 1º",
        text="Este Regulamento é um exemplo.",
        path=(title, "Art. 1º"),
        ordinal=0,
    )
    document = Document(
        id="res-anpd-9-2099",
        title="Resolução sintética",
        kind=DocumentKind.RESOLUTION,
        source_url="https://example.org/res",
        source_sha256="b" * 64,
        retrieved_at="2026-09-27",  # type: ignore[arg-type]
        redistribution_basis="test",
        provisions=(article,),
    )
    chunks = chunk_document(document, "Res. sintética")
    vectors = HashingEmbedder().embed_documents([c.content for c in chunks])
    store.replace_document(document, chunks, vectors, "test-hashing")
    assert store.annex_titles() == [("res-anpd-9-2099", "1", title)]
