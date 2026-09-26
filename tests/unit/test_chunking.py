from pathlib import Path

from base_legal.chunking.chunker import MAX_ANCESTOR_CHARS, _clip, chunk_document
from base_legal.corpus.html import decode_html, html_to_lines
from base_legal.corpus.models import Document, DocumentKind
from base_legal.corpus.parser import StructureParser


def _document(fixtures_dir: Path) -> Document:
    raw = (fixtures_dir / "planalto_synthetic.html").read_bytes()
    provisions = StructureParser("lgpd").parse(html_to_lines(decode_html(raw)))
    return Document(
        id="lgpd",
        title="LGPD",
        kind=DocumentKind.LAW,
        source_url="https://example.org",
        source_sha256="0" * 64,
        retrieved_at="2026-09-26",  # type: ignore[arg-type]
        redistribution_basis="test",
        provisions=tuple(provisions),
    )


def test_chunk_content_has_path_ancestors_and_text(fixtures_dir: Path) -> None:
    chunks = {c.provision_id: c for c in chunk_document(_document(fixtures_dir), "LGPD")}
    content = chunks["lgpd:art5:incI"].content.splitlines()
    assert content[0] == "LGPD > CAPÍTULO I — DISPOSIÇÕES PRELIMINARES > Art. 5º > I"
    assert content[1] == "Para os fins desta Lei, considera-se:"
    assert content[2].startswith("dado pessoal: informação relacionada a pessoa natural")


def test_revoked_provisions_are_not_chunked(fixtures_dir: Path) -> None:
    ids = {c.provision_id for c in chunk_document(_document(fixtures_dir), "LGPD")}
    assert "lgpd:art7:par1" not in ids
    assert "lgpd:art7:incIX" in ids


def test_clip() -> None:
    assert _clip("curto", 10) == "curto"
    clipped = _clip("palavra " * 100, MAX_ANCESTOR_CHARS)
    assert len(clipped) <= MAX_ANCESTOR_CHARS
    assert clipped.endswith("…")
