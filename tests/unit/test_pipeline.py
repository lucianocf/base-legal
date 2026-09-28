import datetime as dt
from pathlib import Path

import httpx
import pytest

from base_legal.corpus.manifest import Manifest, ManifestEntry, sha256_hex
from base_legal.corpus.models import DocumentKind
from base_legal.corpus.pipeline import (
    IntegrityError,
    build,
    fetch,
    load_documents,
    write_document,
)


def _entry(**overrides: object) -> ManifestEntry:
    data: dict[str, object] = {
        "id": "lgpd",
        "title": "LGPD",
        "short_name": "LGPD",
        "kind": DocumentKind.LAW,
        "source_url": "https://example.org/l13709.htm",
    }
    data.update(overrides)
    return ManifestEntry.model_validate(data)


def _client(body: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "base-legal/" in request.headers["User-Agent"]
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_records_hash_and_date(tmp_path: Path, fixtures_dir: Path) -> None:
    body = (fixtures_dir / "planalto_synthetic.html").read_bytes()
    updated, result = fetch(_entry(), tmp_path, _client(body), today=dt.date(2026, 9, 26))
    assert result.changed
    assert updated.source_sha256 == sha256_hex(body) == result.sha256
    assert updated.retrieved_at == dt.date(2026, 9, 26)
    assert result.path.read_bytes() == body

    _, again = fetch(updated, tmp_path, _client(body))
    assert not again.changed


def test_fetch_raises_on_http_error(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        fetch(_entry(), tmp_path, client)


def test_build_verifies_hash(tmp_path: Path, fixtures_dir: Path) -> None:
    body = (fixtures_dir / "planalto_synthetic.html").read_bytes()
    entry, _ = fetch(_entry(), tmp_path, _client(body), today=dt.date(2026, 9, 26))

    document = build(entry, tmp_path)
    assert document.source_sha256 == entry.source_sha256
    assert "lgpd:art7:incIX" in document.by_id()
    assert "lgpd:art7:par1" not in {p.id for p in document.in_force()}

    (tmp_path / "lgpd.html").write_bytes(body + b"tampered")
    with pytest.raises(IntegrityError, match="hash"):
        build(entry, tmp_path)


def test_build_requires_fetch(tmp_path: Path) -> None:
    with pytest.raises(IntegrityError, match="not fetched"):
        build(_entry(), tmp_path)


def test_write_and_load_round_trip(tmp_path: Path, fixtures_dir: Path) -> None:
    body = (fixtures_dir / "planalto_synthetic.html").read_bytes()
    raw_dir = tmp_path / "raw"
    entry, _ = fetch(_entry(), raw_dir, _client(body), today=dt.date(2026, 9, 26))
    document = build(entry, raw_dir)
    write_document(document, tmp_path)

    manifest = Manifest(documents=[entry])
    manifest.dump(tmp_path / "manifest.yaml")
    reloaded = Manifest.load(tmp_path / "manifest.yaml")
    assert load_documents(tmp_path, reloaded) == [document]

    stale = Manifest(documents=[entry.model_copy(update={"source_sha256": "0" * 64})])
    with pytest.raises(IntegrityError, match="stale"):
        load_documents(tmp_path, stale)


def test_repo_manifest_is_valid() -> None:
    manifest = Manifest.load(Path(__file__).parents[2] / "corpus" / "manifest.yaml")
    assert manifest.get("lgpd").short_name == "LGPD"


def test_committed_corpus_matches_the_manifest() -> None:
    corpus = Path(__file__).parents[2] / "corpus"
    manifest = Manifest.load(corpus / "manifest.yaml")
    documents = {d.id: d for d in load_documents(corpus, manifest)}
    assert set(documents) == {e.id for e in manifest.documents}
    for entry in manifest.documents:
        assert entry.embeddings == [], "vectors are not redistributed (ADR 0009)"
    # Regulations live in the annex of each resolution (ADR 0010).
    incident = documents["res-anpd-15-2024"].by_id()["res-anpd-15-2024:anx1:art6"]
    assert "três dias úteis" in incident.text
    assert documents["lgpd"].by_id()["lgpd:art7:incIX"].is_normative


def test_committed_history_matches_the_manifest() -> None:
    from base_legal.corpus.history import DocumentHistory
    from base_legal.corpus.pipeline import history_path

    root = Path(__file__).parents[2] / "corpus"
    manifest = Manifest.load(root / "manifest.yaml")
    found = 0
    for entry in manifest.documents:
        path = history_path(root, entry.id)
        if path.exists():
            history = DocumentHistory.model_validate_json(path.read_text(encoding="utf-8"))
            assert history.source_sha256 == entry.source_sha256
            found += 1
    assert found >= 1
