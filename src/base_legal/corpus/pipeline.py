"""Corpus pipeline: ``fetch`` (download + hash) and ``build`` (parse -> JSON).

The two steps are separate on purpose: ``fetch`` touches the network and is
reviewed as a diff of ``manifest.yaml``; ``build`` is deterministic and runs
from the raw file, so CI never depends on government websites.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

from base_legal.corpus.acts import ActsFile
from base_legal.corpus.history import DocumentHistory, extract_history
from base_legal.corpus.html import decode_html, html_to_blocks, html_to_lines
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
    updated, data = download(entry, client, today)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_path(raw_dir, entry.id)
    path.write_bytes(data)
    digest = str(updated.source_sha256)
    return updated, FetchResult(entry.id, path, digest, digest != entry.source_sha256)


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
    return parse_source(entry, data)


def download(
    entry: ManifestEntry, client: httpx.Client, today: dt.date | None = None
) -> tuple[ManifestEntry, bytes]:
    """Download one official source; return the entry updated with its hash and date."""
    response = client.get(str(entry.source_url), headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    data = response.content
    updated = entry.model_copy(
        update={"source_sha256": sha256_hex(data), "retrieved_at": today or dt.date.today()}
    )
    return updated, data


def parse_source(entry: ManifestEntry, data: bytes) -> Document:
    """Parse raw source bytes (whose hash ``entry`` records) into a :class:`Document`."""
    if entry.retrieved_at is None:
        raise IntegrityError(f"{entry.id}: not fetched yet (no date in manifest)")
    digest = sha256_hex(data)
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


def build_history(entry: ManifestEntry, raw_dir: Path, document: Document) -> DocumentHistory:
    """Earlier wordings of ``document``'s provisions from its raw compiled page (ADR 0014)."""
    data = raw_path(raw_dir, entry.id).read_bytes()
    if sha256_hex(data) != document.source_sha256:
        raise IntegrityError(f"{entry.id}: raw file does not match the built document")
    blocks = html_to_blocks(decode_html(data), entry.layout)
    parser = StructureParser(entry.id)
    provisions = parser.parse([text if not struck else "" for text, struck in blocks])
    if tuple(provisions) != document.provisions:
        raise IntegrityError(f"{entry.id}: history parse differs from the built document")
    return extract_history(blocks, document, parser.start_lines)


def history_path(corpus_dir: Path, doc_id: str) -> Path:
    return corpus_dir / "history" / f"{doc_id}.json"


def load_histories(corpus_dir: Path, doc_ids: Iterable[str]) -> dict[str, DocumentHistory]:
    histories: dict[str, DocumentHistory] = {}
    for doc_id in doc_ids:
        path = history_path(corpus_dir, doc_id)
        if path.exists():
            histories[doc_id] = DocumentHistory.model_validate_json(path.read_text("utf-8"))
    return histories


def load_acts(corpus_dir: Path) -> ActsFile:
    path = corpus_dir / "acts.yaml"
    if not path.exists():
        return ActsFile(acts=())
    return ActsFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def dump_acts(acts: ActsFile, corpus_dir: Path) -> Path:
    path = corpus_dir / "acts.yaml"
    header = (
        "# Amending acts cited by the compiled texts and when their wordings came into\n"
        "# force (ADR 0014). Written by `base-legal corpus acts` from each act's own page\n"
        "# on planalto.gov.br; review changes as a diff. `in_force_from: null` means the\n"
        "# date could not be established from the page (see `review`).\n"
    )
    body = yaml.safe_dump(acts.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
    path.write_text(header + body, encoding="utf-8")
    return path


def write_history(history: DocumentHistory, corpus_dir: Path) -> Path:
    path = history_path(corpus_dir, history.document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(history.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


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
