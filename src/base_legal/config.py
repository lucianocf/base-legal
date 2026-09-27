"""Runtime configuration from environment variables (safe defaults)."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from base_legal.retrieval.search import Tuning


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
    # Local model weights, pinned by revision + SHA-256 (src/base_legal/embeddings/*.lock.json).
    models_dir: Path = Path("models")

    top_k: int = 8
    candidate_pool: int = 50
    # Minimum best dense similarity to answer; below it, refuse (ADR 0005).
    # None disables the score check (explicit nonexistent references still refuse).
    refusal_threshold: float | None = 0.40
    # Retrieval knobs, chosen on the golden dev split and confirmed on holdout
    # (docs/evals/retrieval-tuning.md): length-normalized full-text rank
    # (ts_rank_cd flag 4), full-text weighted half of dense in RRF, and 0.2 of
    # each hit's score propagated to its ancestors.
    fts_normalization: int = 4
    lexical_weight: float = 0.5
    dense_weight: float = 1.0
    parent_weight: float = 0.2

    # Generation (ADR 0008): model from configuration, never hardcoded in logic.
    model: str = "claude-haiku-4-5"
    max_answer_tokens: int = Field(default=1024, ge=64, le=4096)

    def tuning(self) -> Tuning:
        return Tuning(
            fts_normalization=self.fts_normalization,
            lexical_weight=self.lexical_weight,
            dense_weight=self.dense_weight,
            parent_weight=self.parent_weight,
        )
