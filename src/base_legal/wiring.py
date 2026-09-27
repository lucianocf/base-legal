"""Build the library's services from settings (shared by the CLI, API and MCP server)."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

from base_legal.config import Settings
from base_legal.corpus.history import ProvisionHistory
from base_legal.corpus.models import Provision
from base_legal.corpus.xrefs import CrossReference, find_candidates, regulation_index, resolve
from base_legal.embeddings.base import Embedder, check_compatible
from base_legal.embeddings.factory import make_query_embedder
from base_legal.generation.answer import Answer, Answerer
from base_legal.retrieval.search import Retriever, SearchResult
from base_legal.store.db import Store


class GenerationUnavailableError(RuntimeError):
    """Claude could not be called (no credentials, network, API error). Content-free."""


def open_store(settings: Settings) -> Store:
    """Connect and make sure the (idempotent) schema exists, so every command and
    the API work on a fresh database, before the first ``ingest``."""
    store = Store.connect(settings.database_url)
    store.init_schema()
    return store


def make_retriever(settings: Settings, store: Store, embedder: Embedder | None = None) -> Retriever:
    embedder = embedder or make_query_embedder(settings)
    meta = store.get_meta()
    if meta:  # shared-space guard (ADR 0003): refuse to mix embedding spaces
        check_compatible(meta["embedding_family"], int(meta["embedding_dim"]), embedder)
    return Retriever(
        store, embedder, candidate_pool=settings.candidate_pool, tuning=settings.tuning()
    )


def make_answerer(settings: Settings, store: Store, retriever: Retriever | None = None) -> Answerer:
    import anthropic  # credentials come from the environment, never from files

    return Answerer(
        retriever or make_retriever(settings, store),
        store,
        _GuardedClient(anthropic.Anthropic()),
        model=settings.model,
        max_tokens=settings.max_answer_tokens,
        k=settings.top_k,
        threshold=settings.refusal_threshold,
    )


class _GuardedMessages:
    def __init__(self, messages: Any) -> None:  # Any: anthropic.resources.Messages
        self._messages = messages

    def create(self, **kwargs: Any) -> Any:  # Any: anthropic.types.Message
        import anthropic

        try:
            return self._messages.create(**kwargs)
        except anthropic.APIError as error:
            raise GenerationUnavailableError(type(error).__name__) from None
        except TypeError as error:
            # The SDK raises a bare TypeError when no credential resolves.
            if "authentication method" in str(error):
                raise GenerationUnavailableError("no Anthropic credentials") from None
            raise


class _GuardedClient:
    def __init__(self, client: Any) -> None:  # Any: anthropic.Anthropic
        self.messages = _GuardedMessages(client.messages)


class DatabaseBackend:
    """The API/MCP backend: one connection, serialized (a local, single-user tool)."""

    def __init__(self, settings: Settings, *, with_generation: bool = True) -> None:
        self.settings = settings
        self.store = open_store(settings)
        self.retriever = make_retriever(settings, self.store)
        self.answerer = (
            make_answerer(settings, self.store, self.retriever) if with_generation else None
        )
        self._lock = threading.Lock()
        self._regulations: dict[str, tuple[str, str]] | None = None

    def search(self, question: str, k: int) -> SearchResult:
        """``question`` must already be redacted."""
        with self._lock:
            return self.retriever.search(question, k=k)

    def answer(self, question: str) -> Answer:
        if self.answerer is None:
            raise GenerationUnavailableError("generation disabled")
        with self._lock:
            return self.answerer.answer(question)

    def provision(self, provision_id: str) -> Provision | None:
        with self._lock:
            return self.store.provisions([provision_id]).get(provision_id)

    def history(self, provision_id: str) -> ProvisionHistory | None:
        with self._lock:
            return self.store.history(provision_id)

    def references(self, texts: Mapping[str, str]) -> dict[str, tuple[CrossReference, ...]]:
        """Cross-references in each provision's text (id -> text) that resolve in the index."""
        with self._lock:
            if self._regulations is None:
                self._regulations = regulation_index(self.store.annex_titles())
            candidates = {
                pid: find_candidates(pid, text, self._regulations) for pid, text in texts.items()
            }
            wanted = {t for found in candidates.values() for c in found for t in c.targets}
            existing = self.store.normative_ids(sorted(wanted))
        return {pid: resolve(pid, found, existing) for pid, found in candidates.items()}

    def health(self) -> dict[str, str]:
        with self._lock:
            meta = self.store.get_meta()
            models = self.store.document_embedding_models()
        return {
            "embedding_family": meta.get("embedding_family", "none"),
            "document_embedding_models": models or "none",
            "provisions_indexed": str(self.store_count()),
            "generation_model": self.settings.model,
        }

    def store_count(self) -> int:
        return self.store.count_chunks()

    def close(self) -> None:
        self.store.close()
