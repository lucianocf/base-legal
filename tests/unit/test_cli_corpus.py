import datetime as dt
import shutil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from base_legal.cli import app as cli
from base_legal.corpus.manifest import Manifest, ManifestEntry, sha256_hex
from base_legal.corpus.models import DocumentKind
from base_legal.embeddings.base import EMBEDDING_DIM
from base_legal.embeddings.precomputed import local_artifact
from base_legal.embeddings.providers import VoyageApiEmbedder


class _Result:
    def __init__(self, n: int) -> None:
        self.embeddings = [[1.0] + [0.0] * (EMBEDDING_DIM - 1)] * n


class _FakeVoyage:
    def embed(self, texts: list[str], **_: Any) -> _Result:
        return _Result(len(texts))


@pytest.fixture
def corpus_dir(tmp_path: Path, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    corpus, raw = tmp_path / "corpus", tmp_path / "corpus" / "raw"
    raw.mkdir(parents=True)
    shutil.copy(fixtures_dir / "planalto_synthetic.html", raw / "lgpd.html")
    Manifest(
        documents=[
            ManifestEntry(
                id="lgpd",
                title="LGPD (synthetic fixture)",
                short_name="LGPD",
                kind=DocumentKind.LAW,
                source_url="https://example.org/l13709.htm",  # type: ignore[arg-type]
                retrieved_at=dt.date(2026, 9, 26),
                source_sha256=sha256_hex((raw / "lgpd.html").read_bytes()),
            )
        ]
    ).dump(corpus / "manifest.yaml")
    (corpus / "manifest.yaml").write_text(
        "# Provenance of the corpus (kept by Manifest.dump)\n"
        + (corpus / "manifest.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("BASE_LEGAL_CORPUS_DIR", str(corpus))
    monkeypatch.setenv("BASE_LEGAL_RAW_DIR", str(raw))
    monkeypatch.setattr(
        cli,
        "make_api_document_embedder",
        lambda _settings: VoyageApiEmbedder(api_key="unused", client=_FakeVoyage()),
    )
    assert CliRunner().invoke(cli.app, ["corpus", "build"]).exit_code == 0
    return corpus


def test_embed_without_record_leaves_the_manifest_alone(corpus_dir: Path) -> None:
    before = (corpus_dir / "manifest.yaml").read_text(encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["corpus", "embed"])
    assert result.exit_code == 0, result.output
    assert (corpus_dir / "manifest.yaml").read_text(encoding="utf-8") == before
    artifact = local_artifact(corpus_dir / "embeddings", "lgpd", "voyage-4-large")
    assert artifact is not None
    assert (corpus_dir / "embeddings" / artifact.file).is_file()


def test_embed_with_record_updates_the_manifest_and_keeps_comments(corpus_dir: Path) -> None:
    result = CliRunner().invoke(cli.app, ["corpus", "embed", "--record"])
    assert result.exit_code == 0, result.output
    text = (corpus_dir / "manifest.yaml").read_text(encoding="utf-8")
    # Regression: Manifest.dump used to drop the file's comments.
    assert text.startswith("# Provenance of the corpus")
    (artifact,) = Manifest.load(corpus_dir / "manifest.yaml").get("lgpd").embeddings
    assert artifact.model == "voyage-4-large"
    assert local_artifact(corpus_dir / "embeddings", "lgpd", "voyage-4-large") is None
