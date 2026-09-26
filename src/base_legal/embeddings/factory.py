"""Build embedders from settings."""

from __future__ import annotations

from base_legal.config import Settings
from base_legal.embeddings.base import Embedder
from base_legal.embeddings.providers import (
    HashingEmbedder,
    LocalSentenceTransformerEmbedder,
    VoyageApiEmbedder,
)

TEST_EMBEDDER = "test-hashing"


def make_query_embedder(settings: Settings) -> Embedder:
    """Local only: user questions never go to an embedding API (ADR 0003)."""
    if settings.query_embedder == TEST_EMBEDDER:
        return HashingEmbedder()
    return LocalSentenceTransformerEmbedder(
        repo=settings.query_model_repo,
        model=settings.query_embedder,
        revision=settings.query_model_revision,
    )


def make_api_document_embedder(settings: Settings) -> VoyageApiEmbedder:
    if settings.voyage_api_key is None:
        raise RuntimeError("VOYAGE_API_KEY is required to embed documents via the API")
    return VoyageApiEmbedder(
        api_key=settings.voyage_api_key.get_secret_value(), model=settings.document_embedder
    )


def make_local_document_embedder(settings: Settings) -> Embedder:
    """Fully offline mode: documents embedded with the local query model too."""
    return make_query_embedder(settings)
