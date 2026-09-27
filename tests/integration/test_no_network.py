"""The query path makes no network call: questions never leave the machine
for embedding (ADR 0003; PLAN §9 "a test proves the query path makes no
network call to Voyage")."""

import ipaddress
import socket
from pathlib import Path
from typing import Any

import anthropic
import pytest
from typer.testing import CliRunner

from base_legal.cli.app import app
from base_legal.config import IngestMode, Settings
from base_legal.corpus.manifest import Manifest
from base_legal.corpus.models import Document
from base_legal.embeddings.factory import make_query_embedder
from base_legal.embeddings.providers import HashingEmbedder, VoyageApiEmbedder
from base_legal.ingest import ingest_documents
from base_legal.store.db import Store

pytestmark = pytest.mark.integration


def _forbid_remote_connections(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    # Without proxies every HTTP client must dial the remote host itself, so a
    # call to Voyage (or anyone) cannot hide behind a loopback proxy.
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    attempts: list[object] = []
    original = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else None
        if host is not None:
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = host == "localhost"
            if not local:
                attempts.append(address)
                raise ConnectionRefusedError(f"network call to {address!r} in the query path")
        return original(self, address)  # Unix sockets and loopback (the database)

    monkeypatch.setattr(socket.socket, "connect", connect)
    return attempts


def test_query_embedder_is_never_the_voyage_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "a-real-looking-key")
    monkeypatch.setenv("BASE_LEGAL_QUERY_EMBEDDER", "test-hashing")
    embedder = make_query_embedder(Settings())
    assert not isinstance(embedder, VoyageApiEmbedder)
    with pytest.raises(RuntimeError, match="embedded locally"):
        VoyageApiEmbedder(api_key="k", client=object()).embed_query("Meu CPF vazou?")


def test_search_and_ask_make_no_remote_connection(
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

    class _OfflineClaude:  # generation is Anthropic's job; here we only watch the network
        def __init__(self) -> None:
            self.messages = self

        def create(self, **_: Any) -> anthropic.types.Message:
            return anthropic.types.Message.model_validate(
                {
                    "id": "m",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-haiku-4-5",
                    "content": [{"type": "text", "text": "SEM_BASE"}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            )

    for key, value in {
        "DATABASE_URL": database_url,
        "BASE_LEGAL_QUERY_EMBEDDER": "test-hashing",
        "VOYAGE_API_KEY": "a-real-looking-key",
        "BASE_LEGAL_REFUSAL_THRESHOLD": "0",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(anthropic, "Anthropic", _OfflineClaude)
    attempts = _forbid_remote_connections(monkeypatch)
    runner = CliRunner()
    search = runner.invoke(app, ["search", "legítimo interesse do controlador"])
    assert search.exit_code == 0, search.output
    ask = runner.invoke(app, ["ask", "legítimo interesse do controlador"])
    assert ask.exit_code == 0, ask.output
    assert attempts == []


def test_the_guard_catches_a_remote_call(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = _forbid_remote_connections(monkeypatch)
    with socket.socket() as sock, pytest.raises(ConnectionRefusedError):
        sock.connect(("203.0.113.10", 443))  # TEST-NET-3, never routed
    assert attempts == [("203.0.113.10", 443)]
