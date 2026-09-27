"""Corpus pipeline: ``fetch`` (download + hash) and ``build`` (parse -> JSON).

The two steps are separate on purpose: ``fetch`` touches the network and is
reviewed as a diff of ``manifest.yaml``; ``build`` is deterministic and runs
from the raw file, so CI never depends on government websites.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import httpx

from base_legal.corpus.html import decode_html, html_to_lines
from base_legal.corpus.manifest import Manifest, ManifestEntry, sha256_hex
from base_legal.corpus.models import Document
from base_legal.corpus.parser import StructureParser

# Planalto rejects user agents that do not start with "Mozilla/"; the
# "compatible" form still identifies the project honestly, as crawlers do.
USER_AGENT = "Mozilla/5.0 (compatible; base-legal/0.1; +https://github.com/lucianocf/base-legal)"


class IntegrityError(RuntimeError):
    """Raw source bytes do not match the hash recorded in the manifest."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    doc_id: str
    path: Path
    sha256: str
    changed: bool


def raw_path(raw_dir: Path, doc_id: str) -> Path:
    return raw_dir / f"{doc_id}.html"


def fetch(
    entry: ManifestEntry,
    raw_dir: Path,
    client: httpx.Client,
    today: dt.date | None = None,
) -> tuple[ManifestEntry, FetchResult]:
    """Download one official source and return the updated manifest entry."""
    response = client.get(str(entry.source_url), headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    data = response.content
    digest = sha256_hex(data)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_path(raw_dir, entry.id)
    path.write_bytes(data)
    changed = digest != entry.source_sha256
    updated = entry.model_copy(
        update={"source_sha256": digest, "retrieved_at": today or dt.date.today()}
    )
    return updated, FetchResult(entry.id, path, digest, changed)


def build(entry: ManifestEntry, raw_dir: Path) -> Document:
    """Parse the raw source into a normalized :class:`Document`, verifying its hash."""
    if entry.source_sha256 is None or entry.retrieved_at is None:
        raise IntegrityError(f"{entry.id}: not fetched yet (no hash in manifest)")
    data = raw_path(raw_dir, entry.id).read_bytes()
    digest = sha256_hex(data)
    if digest != entry.source_sha256:
        raise IntegrityError(
            f"{entry.id}: raw file hash {digest} != manifest {entry.source_sha256}"
        )
    lines = html_to_lines(decode_html(data), entry.layout)
    provisions = StructureParser(entry.id).parse(lines)
    return Document(
        id=entry.id,
        title=entry.title,
        kind=entry.kind,
        source_url=str(entry.source_url),
        source_sha256=digest,
        retrieved_at=entry.retrieved_at,
        redistribution_basis=entry.redistribution_basis,
        provisions=tuple(provisions),
    )


def document_path(corpus_dir: Path, doc_id: str) -> Path:
    return corpus_dir / f"{doc_id}.json"


def write_document(document: Document, corpus_dir: Path) -> Path:
    path = document_path(corpus_dir, document.id)
    path.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_documents(corpus_dir: Path, manifest: Manifest) -> list[Document]:
    """Load every built document listed in the manifest, checking provenance."""
    documents: list[Document] = []
    for entry in manifest.documents:
        path = document_path(corpus_dir, entry.id)
        if not path.exists():
            continue
        document = Document.model_validate_json(path.read_text(encoding="utf-8"))
        if document.source_sha256 != entry.source_sha256:
            raise IntegrityError(f"{entry.id}: built JSON is stale vs manifest hash")
        documents.append(document)
    return documents
