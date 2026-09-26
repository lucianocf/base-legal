import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from base_legal.corpus.html import decode_html, html_to_lines
from base_legal.corpus.manifest import Manifest, ManifestEntry
from base_legal.corpus.models import Document, DocumentKind
from base_legal.corpus.parser import StructureParser
from base_legal.store.db import Store

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.integration


@pytest.fixture
def store() -> Iterator[Store]:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set (PostgreSQL with pgvector required)")
    store = Store.connect(DATABASE_URL)
    with store.conn.transaction():
        store.conn.execute(
            b"DROP TABLE IF EXISTS chunks, provisions, documents, index_meta CASCADE"
        )
    store.init_schema()
    yield store
    store.close()


@pytest.fixture
def document(fixtures_dir: Path) -> Document:
    raw = (fixtures_dir / "planalto_synthetic.html").read_bytes()
    provisions = StructureParser("lgpd").parse(html_to_lines(decode_html(raw)))
    return Document(
        id="lgpd",
        title="LGPD (synthetic fixture)",
        kind=DocumentKind.LAW,
        source_url="https://example.org/l13709.htm",
        source_sha256="a" * 64,
        retrieved_at="2026-09-26",  # type: ignore[arg-type]
        redistribution_basis="test",
        provisions=tuple(provisions),
    )


@pytest.fixture
def manifest() -> Manifest:
    entry = ManifestEntry(
        id="lgpd",
        title="LGPD",
        short_name="LGPD",
        kind=DocumentKind.LAW,
        source_url="https://example.org/l13709.htm",  # type: ignore[arg-type]
        source_sha256="a" * 64,
        retrieved_at="2026-09-26",  # type: ignore[arg-type]
    )
    return Manifest(documents=[entry])
