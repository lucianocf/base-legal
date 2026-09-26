"""``corpus/manifest.yaml``: provenance of every document in the corpus.

Each entry records where the official text came from, when it was retrieved,
the SHA-256 of the raw bytes, and the legal basis for redistributing it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from base_legal.corpus.models import DocumentKind

DEFAULT_REDISTRIBUTION_BASIS = (
    "Lei nº 9.610/1998, art. 8º, IV: official acts are not protected by copyright"
)


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    short_name: str = Field(description='Prefix used in chunk paths, e.g. "LGPD"')
    kind: DocumentKind
    source_url: HttpUrl
    redistribution_basis: str = DEFAULT_REDISTRIBUTION_BASIS
    retrieved_at: dt.date | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[ManifestEntry]

    def get(self, doc_id: str) -> ManifestEntry:
        for entry in self.documents:
            if entry.id == doc_id:
                return entry
        raise KeyError(doc_id)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def dump(self, path: Path) -> None:
        data = self.model_dump(mode="json")
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
