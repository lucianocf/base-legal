import datetime as dt
import importlib.util
import shutil
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest
from typer.testing import CliRunner

from base_legal.cli.app import app
from base_legal.config import IngestMode
from base_legal.corpus.manifest import Manifest, ManifestEntry, sha256_hex
from base_legal.corpus.models import Document, DocumentKind
from base_legal.embeddings.providers import HashingEmbedder
from base_legal.ingest import ingest_documents
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
    assert "no support in the corpus (nonexistent_provision)" in result.output

    # Regression: `search` listed hits for out-of-scope questions without
    # saying that `ask` and the API refuse them (ADR 0016).
    result = runner.invoke(app, ["search", "Qual é a pena de furto no Código Penal?"])
    assert result.exit_code == 0, result.output
    assert "no support in the corpus (out_of_scope)" in result.output


def test_unknown_doc_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text("documents: []\n", encoding="utf-8")
    monkeypatch.setenv("BASE_LEGAL_CORPUS_DIR", str(tmp_path))
    result = CliRunner().invoke(app, ["corpus", "build", "--doc", "nope"])
    assert result.exit_code != 0


def test_eval_retrieval_writes_reports(
    store: Store,
    database_url: str,
    fixtures_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus_dir, raw_dir = tmp_path / "corpus", tmp_path / "corpus" / "raw"
    raw_dir.mkdir(parents=True)
    shutil.copy(fixtures_dir / "planalto_synthetic.html", raw_dir / "lgpd.html")
    Manifest(
        documents=[
            ManifestEntry(
                id="lgpd",
                title="LGPD (synthetic fixture)",
                short_name="LGPD",
                kind=DocumentKind.LAW,
                source_url="https://example.org/l13709.htm",  # type: ignore[arg-type]
                retrieved_at=dt.date(2026, 9, 26),
                source_sha256=sha256_hex((raw_dir / "lgpd.html").read_bytes()),
            )
        ]
    ).dump(corpus_dir / "manifest.yaml")
    golden = tmp_path / "golden.yaml"
    golden.write_text(
        "version: 1\n"
        "answerable:\n"
        "  - {id: a1, question: 'O que diz o art. 7º, IX?', expected: [lgpd:art7:incIX],"
        " split: dev, status: unverified}\n"
        "  - {id: a2, question: 'prevenção à fraude', expected: [lgpd:art11:incII:alig],"
        " split: holdout, status: unverified}\n"
        "refuse:\n"
        "  - {id: r1, question: 'O que diz o art. 99?', reason: nonexistent_provision,"
        " split: dev, status: unverified}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("BASE_LEGAL_CORPUS_DIR", str(corpus_dir))
    monkeypatch.setenv("BASE_LEGAL_RAW_DIR", str(raw_dir))
    monkeypatch.setenv("BASE_LEGAL_QUERY_EMBEDDER", "test-hashing")
    runner = CliRunner()
    assert runner.invoke(app, ["corpus", "build"]).exit_code == 0
    assert runner.invoke(app, ["ingest", "--mode", "local"]).exit_code == 0

    out = tmp_path / "reports"
    args = ["eval", "retrieval", "--golden", str(golden), "--out-dir", str(out), "--label", "t"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "| recall@1 | 100.0 % |" in result.output
    assert "| Refusal accuracy (must-refuse) | 100.0 % |" in result.output
    assert (out / "retrieval-t-dev.json").is_file()
    assert (out / "retrieval-t-dev.md").is_file()

    badge = tmp_path / "badges" / "recall.json"
    result = runner.invoke(app, [*args, "--badge", str(badge), "--min-recall-at-5", "0.9"])
    assert result.exit_code == 0, result.output
    assert '"label": "recall@5"' in badge.read_text(encoding="utf-8")
    result = runner.invoke(
        app, [*args, "--min-recall-at-5", "1.01", "--min-refusal-accuracy", "1.01"]
    )
    assert result.exit_code == 1
    assert "Eval gate failed" in result.output

    result = runner.invoke(app, [*args, "--mode", "lexical", "--split", "holdout"])
    assert result.exit_code == 0, result.output
    assert "query_embedder=none" in result.output

    golden.write_text(
        golden.read_text(encoding="utf-8").replace("lgpd:art7:incIX]", "lgpd:art7:incXII]"),
        encoding="utf-8",
    )
    result = runner.invoke(app, args)
    assert result.exit_code != 0
    assert "lgpd:art7:incXII" in result.output


class _EchoMessages:
    """Answers by citing document 0 verbatim, as native Citations would."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> anthropic.types.Message:
        self.calls.append(kwargs)
        first = kwargs["messages"][0]["content"][0]
        cited = first["source"]["content"][0]["text"]
        return anthropic.types.Message.model_validate(
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": kwargs["model"],
                "content": [
                    {
                        "type": "text",
                        "text": "Segundo o dispositivo recuperado, " + cited,
                        "citations": [
                            {
                                "type": "content_block_location",
                                "cited_text": cited,
                                "document_index": 0,
                                "document_title": first["title"],
                                "start_block_index": 0,
                                "end_block_index": 1,
                            }
                        ],
                    }
                ],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )


class _FakeAnthropic:
    last: "_FakeAnthropic | None" = None

    def __init__(self) -> None:
        self.messages = _EchoMessages()
        _FakeAnthropic.last = self


def test_ask_answers_with_verified_citations_or_refuses(
    store: Store,
    database_url: str,
    fixtures_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus_dir, raw_dir = tmp_path / "corpus", tmp_path / "corpus" / "raw"
    raw_dir.mkdir(parents=True)
    shutil.copy(fixtures_dir / "planalto_synthetic.html", raw_dir / "lgpd.html")
    Manifest(
        documents=[
            ManifestEntry(
                id="lgpd",
                title="LGPD (synthetic fixture)",
                short_name="LGPD",
                kind=DocumentKind.LAW,
                source_url="https://example.org/l13709.htm",  # type: ignore[arg-type]
                retrieved_at=dt.date(2026, 9, 26),
                source_sha256=sha256_hex((raw_dir / "lgpd.html").read_bytes()),
            )
        ]
    ).dump(corpus_dir / "manifest.yaml")
    for key, value in {
        "DATABASE_URL": database_url,
        "BASE_LEGAL_CORPUS_DIR": str(corpus_dir),
        "BASE_LEGAL_RAW_DIR": str(raw_dir),
        "BASE_LEGAL_QUERY_EMBEDDER": "test-hashing",
        "BASE_LEGAL_MODEL": "claude-sonnet-5",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)
    runner = CliRunner()
    assert runner.invoke(app, ["corpus", "build"]).exit_code == 0
    assert runner.invoke(app, ["ingest", "--mode", "local"]).exit_code == 0

    result = runner.invoke(app, ["ask", "Meu CPF é 529.982.247-25. O que diz o art. 7º, IX?"])
    assert result.exit_code == 0, result.output
    assert "Fontes (texto oficial):" in result.output
    assert "[1] lgpd:art7:incIX" in result.output
    assert "aconselhamento jurídico" in result.output
    assert "529.982.247-25" not in result.output
    assert _FakeAnthropic.last is not None
    (call,) = _FakeAnthropic.last.messages.calls
    assert call["model"] == "claude-sonnet-5"  # from BASE_LEGAL_MODEL
    assert "529.982.247-25" not in repr(call)

    result = runner.invoke(app, ["ask", "O que diz o art. 99?"])
    assert result.exit_code == 0, result.output
    assert "Sem base no corpus: O dispositivo citado não existe no corpus." in result.output
    assert "lgpd:art99 não existe no corpus" in result.output


def _ingest_fixture(store: Store, document: Document, manifest: Manifest, tmp: Path) -> None:
    ingest_documents(
        store,
        [document],
        manifest,
        embeddings_dir=tmp,
        mode=IngestMode.LOCAL,
        precomputed_model="voyage-4-large",
        document_embedder=HashingEmbedder(),
    )


def test_ask_reports_api_errors_without_content(
    store: Store,
    database_url: str,
    document: Document,
    manifest: Manifest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ingest_fixture(store, document, manifest, tmp_path)
    monkeypatch.setenv("BASE_LEGAL_REFUSAL_THRESHOLD", "0")

    class _FailingMessages:
        def create(self, **_: Any) -> None:
            request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.APIConnectionError(request=request)

    class _Failing:
        def __init__(self) -> None:
            self.messages = _FailingMessages()

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("BASE_LEGAL_QUERY_EMBEDDER", "test-hashing")
    monkeypatch.setattr(anthropic, "Anthropic", _Failing)
    result = CliRunner().invoke(app, ["ask", "pergunta sigilosa"])
    assert result.exit_code == 2
    assert "APIConnectionError" in result.output  # content-free error name
    assert "pergunta sigilosa" not in result.output


def test_ask_without_credentials_exits_cleanly(
    store: Store,
    database_url: str,
    document: Document,
    manifest: Manifest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ingest_fixture(store, document, manifest, tmp_path)

    class _NoCredentials:
        def __init__(self) -> None:
            self.messages = self

        def create(self, **_: Any) -> None:
            raise TypeError("Could not resolve authentication method. Expected one of api_key")

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("BASE_LEGAL_QUERY_EMBEDDER", "test-hashing")
    monkeypatch.setenv("BASE_LEGAL_REFUSAL_THRESHOLD", "0")
    monkeypatch.setattr(anthropic, "Anthropic", _NoCredentials)
    result = CliRunner().invoke(app, ["ask", "dados pessoais"])
    assert result.exit_code == 2
    assert "no Anthropic credentials" in result.output


def test_eval_redteam_without_the_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BASE_LEGAL_CORPUS_DIR", raising=False)  # the committed corpus
    out, badge = tmp_path / "reports", tmp_path / "redteam.json"
    result = CliRunner().invoke(
        app,
        [
            "eval",
            "redteam",
            "--no-with-index",
            "--seed",
            "3",
            "--out-dir",
            str(out),
            "--badge",
            str(badge),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Pass rate: **100.0 %**" in result.output
    assert "skipped" in result.output  # refusal checks need the index
    assert (out / "redteam.json").is_file()
    assert '"message": "100%"' in badge.read_text(encoding="utf-8")


def test_auto_ingest_falls_back_to_local_without_the_voyage_sdk(
    store: Store,
    database_url: str,
    fixtures_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus_dir, raw_dir = tmp_path / "corpus", tmp_path / "corpus" / "raw"
    raw_dir.mkdir(parents=True)
    shutil.copy(fixtures_dir / "planalto_synthetic.html", raw_dir / "lgpd.html")
    Manifest(
        documents=[
            ManifestEntry(
                id="lgpd",
                title="LGPD",
                short_name="LGPD",
                kind=DocumentKind.LAW,
                source_url="https://example.org/l13709.htm",  # type: ignore[arg-type]
                retrieved_at=dt.date(2026, 9, 26),
                source_sha256=sha256_hex((raw_dir / "lgpd.html").read_bytes()),
            )
        ]
    ).dump(corpus_dir / "manifest.yaml")
    for key, value in {
        "DATABASE_URL": database_url,
        "BASE_LEGAL_CORPUS_DIR": str(corpus_dir),
        "BASE_LEGAL_RAW_DIR": str(raw_dir),
        "BASE_LEGAL_QUERY_EMBEDDER": "test-hashing",
        "VOYAGE_API_KEY": "a-key-without-the-sdk",
    }.items():
        monkeypatch.setenv(key, value)
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: None if name == "voyageai" else real_find_spec(name, *a),
    )
    runner = CliRunner()
    assert runner.invoke(app, ["corpus", "build"]).exit_code == 0
    result = runner.invoke(app, ["ingest", "--mode", "auto"])
    assert result.exit_code == 0, result.output
    assert "embedding locally" in result.output
    assert "test-hashing (embedded), ingested" in result.output


@pytest.mark.parametrize(
    "args",
    [["search", "direitos do titular"], ["ask", "O que é dado pessoal?"], ["eval", "retrieval"]],
)
def test_commands_on_an_empty_index_say_so(
    args: list[str], store: Store, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: `search` on a fresh database printed nothing and exited 0.
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("BASE_LEGAL_QUERY_EMBEDDER", "test-hashing")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "run `base-legal ingest` first" in result.output
