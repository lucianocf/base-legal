import datetime as dt
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from base_legal.cli.app import app
from base_legal.corpus.manifest import Manifest, ManifestEntry, sha256_hex
from base_legal.corpus.models import DocumentKind
from base_legal.store.db import Store

pytestmark = pytest.mark.integration


def test_build_ingest_search_end_to_end(
    store: Store,
    database_url: str,
    fixtures_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus_dir, raw_dir = tmp_path / "corpus", tmp_path / "corpus" / "raw"
    raw_dir.mkdir(parents=True)
    raw = raw_dir / "lgpd.html"
    shutil.copy(fixtures_dir / "planalto_synthetic.html", raw)
    Manifest(
        documents=[
            ManifestEntry(
                id="lgpd",
                title="LGPD (synthetic fixture)",
                short_name="LGPD",
                kind=DocumentKind.LAW,
                source_url="https://example.org/l13709.htm",  # type: ignore[arg-type]
                retrieved_at=dt.date(2026, 9, 26),
                source_sha256=sha256_hex(raw.read_bytes()),
            )
        ]
    ).dump(corpus_dir / "manifest.yaml")

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("BASE_LEGAL_CORPUS_DIR", str(corpus_dir))
    monkeypatch.setenv("BASE_LEGAL_RAW_DIR", str(raw_dir))
    monkeypatch.setenv("BASE_LEGAL_QUERY_EMBEDDER", "test-hashing")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    runner = CliRunner()

    result = runner.invoke(app, ["corpus", "build"])
    assert result.exit_code == 0, result.output
    assert "provisions" in result.output

    result = runner.invoke(app, ["ingest", "--mode", "local"])
    assert result.exit_code == 0, result.output
    assert "ingested" in result.output

    result = runner.invoke(app, ["search", "Meu CPF 529.982.247-25 pode ser usado? art. 7º, IX"])
    assert result.exit_code == 0, result.output
    assert "529.982.247-25" not in result.output
    assert "redacted {'CPF': 1}" in result.output
    first = result.output.splitlines()[1]
    assert "lgpd:art7:incIX" in first

    result = runner.invoke(app, ["search", "O que diz o art. 99?"])
    assert "lgpd:art99 does not exist" in result.output


def test_unknown_doc_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text("documents: []\n", encoding="utf-8")
    monkeypatch.setenv("BASE_LEGAL_CORPUS_DIR", str(tmp_path))
    result = CliRunner().invoke(app, ["corpus", "build", "--doc", "nope"])
    assert result.exit_code != 0
