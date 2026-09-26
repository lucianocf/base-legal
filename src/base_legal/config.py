"""Runtime configuration from environment variables (safe defaults)."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestMode(StrEnum):
    AUTO = "auto"
    PRECOMPUTED = "precomputed"
    API = "api"
    LOCAL = "local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BASE_LEGAL_", extra="ignore")

    database_url: str = Field(
        default="postgresql://base_legal:base_legal@localhost:5432/base_legal",
        validation_alias=AliasChoices("BASE_LEGAL_DATABASE_URL", "DATABASE_URL"),
    )
    voyage_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("BASE_LEGAL_VOYAGE_API_KEY", "VOYAGE_API_KEY")
    )
    corpus_dir: Path = Path("corpus")
    raw_dir: Path = Path("corpus/raw")

    ingest_mode: IngestMode = IngestMode.AUTO
    document_embedder: str = "voyage-4-large"
    query_embedder: str = "voyage-4-nano"
    # Hugging Face repo and pinned revision of the local query model (ADR 0003).
    query_model_repo: str = "voyageai/voyage-4-nano"
    query_model_revision: str | None = None

    top_k: int = 8
    candidate_pool: int = 50
