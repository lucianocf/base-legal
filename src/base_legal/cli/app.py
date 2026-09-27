"""``base-legal`` command-line interface."""

from __future__ import annotations

import dataclasses
import datetime as dt
import importlib.util
import logging
from pathlib import Path
from typing import Annotated

import httpx
import typer

from base_legal.chunking.chunker import chunk_document
from base_legal.config import IngestMode, Settings
from base_legal.corpus.history import date_history
from base_legal.corpus.html import decode_html
from base_legal.corpus.manifest import Manifest
from base_legal.corpus.models import Document, SourceLayout
from base_legal.corpus.pipeline import (
    build,
    build_history,
    document_path,
    download,
    fetch,
    load_acts,
    load_documents,
    load_histories,
    parse_source,
    raw_path,
    write_document,
    write_history,
)
from base_legal.corpus.watch import DocumentDiff, diff_documents, render_report
from base_legal.embeddings.base import Embedder
from base_legal.embeddings.factory import (
    make_api_document_embedder,
    make_local_document_embedder,
)
from base_legal.embeddings.model_store import fetch_model, load_lock
from base_legal.embeddings.precomputed import artifact_filename, save_vectors, write_sidecar
from base_legal.evals.badge import write_badge
from base_legal.evals.golden import GoldenSet, Split
from base_legal.evals.redteam import RedTeamSet, run_redteam
from base_legal.evals.redteam import to_markdown as redteam_markdown
from base_legal.evals.retrieval import evaluate, to_markdown
from base_legal.generation.answer import Answer, Status
from base_legal.ingest import ingest_documents
from base_legal.privacy.redact import redact
from base_legal.retrieval.search import SearchMode
from base_legal.store.db import Store
from base_legal.wiring import (
    GenerationUnavailableError,
    make_answerer,
    make_retriever,
    open_store,
)

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
corpus_app = typer.Typer(no_args_is_help=True, help="Maintain the normalized corpus.")
app.add_typer(corpus_app, name="corpus")
model_app = typer.Typer(no_args_is_help=True, help="Manage pinned local model weights.")
app.add_typer(model_app, name="model")
eval_app = typer.Typer(no_args_is_help=True, help="Deterministic evaluations (no paid APIs).")
app.add_typer(eval_app, name="eval")

DocOption = Annotated[
    list[str] | None, typer.Option("--doc", help="Limit to these document ids (repeatable).")
]


def _settings() -> Settings:
    return Settings()


def _manifest_path(settings: Settings) -> Path:
    return settings.corpus_dir / "manifest.yaml"


def _selected(manifest: Manifest, docs: list[str] | None) -> list[str]:
    ids = [e.id for e in manifest.documents]
    if not docs:
        return ids
    unknown = sorted(set(docs) - set(ids))
    if unknown:
        raise typer.BadParameter(f"unknown document id(s): {', '.join(unknown)}")
    return docs


@corpus_app.command("fetch")
def corpus_fetch(doc: DocOption = None) -> None:
    """Download official sources and record their SHA-256 in the manifest."""
    settings = _settings()
    manifest = Manifest.load(_manifest_path(settings))
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for doc_id in _selected(manifest, doc):
            updated, result = fetch(manifest.get(doc_id), settings.raw_dir, client)
            index = next(i for i, e in enumerate(manifest.documents) if e.id == doc_id)
            manifest.documents[index] = updated
            status = "changed" if result.changed else "unchanged"
            typer.echo(f"{doc_id}: {status} sha256={result.sha256}")
    manifest.dump(_manifest_path(settings))


@corpus_app.command("check")
def corpus_check(
    doc: DocOption = None,
    apply: Annotated[
        bool, typer.Option(help="Write changed acts (raw file, manifest entry and JSON).")
    ] = False,
    report: Annotated[
        Path | None, typer.Option(help="Write a Markdown report of the changes here.")
    ] = None,
) -> None:
    """Compare the official sources with the committed corpus, provision by provision.

    Raw hashes alone are ignored (official pages change bytes without changing
    the law); only a change in the parsed provisions counts.
    """
    settings = _settings()
    manifest = Manifest.load(_manifest_path(settings))
    today = dt.date.today()
    diffs: list[DocumentDiff] = []
    selected = _selected(manifest, doc)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for doc_id in selected:
            updated, data = download(manifest.get(doc_id), client, today)
            document = parse_source(updated, data)
            path = document_path(settings.corpus_dir, doc_id)
            old = (
                Document.model_validate_json(path.read_text(encoding="utf-8"))
                if path.exists()
                else None
            )
            diff = diff_documents(old, document)
            diffs.append(diff)
            if not diff.changed:
                typer.echo(f"{doc_id}: no normative change")
                continue
            typer.echo(f"{doc_id}: {len(diff.changes)} provision change(s)")
            if apply:
                raw = raw_path(settings.raw_dir, doc_id)
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_bytes(data)
                index = next(i for i, e in enumerate(manifest.documents) if e.id == doc_id)
                manifest.documents[index] = updated
                write_document(document, settings.corpus_dir)
    if apply and any(d.changed for d in diffs):
        manifest.dump(_manifest_path(settings))
    if report is not None:
        report.write_text(render_report(diffs, selected, today.isoformat()), encoding="utf-8")


@corpus_app.command("acts")
def corpus_acts(
    refresh: Annotated[bool, typer.Option(help="Fetch again acts already recorded.")] = False,
) -> None:
    """Record when each amending act came into force, from its own official page."""
    from base_legal.corpus.acts import act_links, describe, merge
    from base_legal.corpus.pipeline import USER_AGENT, dump_acts, load_acts

    settings = _settings()
    manifest = Manifest.load(_manifest_path(settings))
    known = load_acts(settings.corpus_dir)
    recorded = known.by_name()
    wanted: dict[str, str] = {}
    for entry in manifest.documents:
        path = raw_path(settings.raw_dir, entry.id)
        if entry.layout is SourceLayout.PLANALTO and path.exists():
            html = decode_html(path.read_bytes())
            wanted |= act_links(html, str(entry.source_url))
    today = dt.date.today()
    fetched = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for name, url in sorted(wanted.items()):
            if name in recorded and not refresh:
                continue
            response = client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            act = describe(
                name, str(response.url), decode_html(response.content), response.content, today
            )
            fetched.append(act)
            when = act.in_force_from or f"undated ({act.review})"
            typer.echo(f"{name}: {when}")
    dump_acts(merge(known.acts, fetched), settings.corpus_dir)


@corpus_app.command("explorer")
def corpus_explorer(
    out: Annotated[Path, typer.Option(help="Directory for the static site.")] = Path(
        "site/explorer"
    ),
) -> None:
    """Build the static corpus explorer (one page per act, anchors, links, search)."""
    from base_legal.explorer.site import build_site

    settings = _settings()
    documents = load_documents(settings.corpus_dir, Manifest.load(_manifest_path(settings)))
    histories = load_histories(settings.corpus_dir, [d.id for d in documents])
    out.mkdir(parents=True, exist_ok=True)
    for name, content in build_site(documents, histories).items():
        (out / name).write_text(content, encoding="utf-8")
    typer.echo(f"{len(documents)} act(s) -> {out}")


@corpus_app.command("build")
def corpus_build(doc: DocOption = None) -> None:
    """Parse raw sources into normalized JSON under the corpus directory."""
    settings = _settings()
    manifest = Manifest.load(_manifest_path(settings))
    for doc_id in _selected(manifest, doc):
        entry = manifest.get(doc_id)
        document = build(entry, settings.raw_dir)
        path = write_document(document, settings.corpus_dir)
        if entry.layout is SourceLayout.PLANALTO:
            acts = {a.name: a.in_force_from for a in load_acts(settings.corpus_dir).acts}
            history = date_history(build_history(entry, settings.raw_dir, document), acts)
            write_history(history, settings.corpus_dir)
            typer.echo(f"{doc_id}: earlier wordings of {len(history.provisions)} provision(s)")
        in_force = len(document.in_force())
        typer.echo(
            f"{doc_id}: {len(document.provisions)} provisions ({in_force} in force) -> {path}"
        )


@corpus_app.command("embed")
def corpus_embed(
    doc: DocOption = None,
    record: Annotated[
        bool,
        typer.Option(
            help="Record the vectors in manifest.yaml (only once they may be redistributed, "
            "ADR 0009). Otherwise a git-ignored sidecar next to the vectors records the hash."
        ),
    ] = False,
) -> None:
    """Maintainers: embed the PUBLIC law text via the Voyage API and store the vectors."""
    settings = _settings()
    manifest = Manifest.load(_manifest_path(settings))
    embedder = make_api_document_embedder(settings)
    embeddings_dir = settings.corpus_dir / "embeddings"
    selected = set(_selected(manifest, doc))
    for document in load_documents(settings.corpus_dir, manifest):
        if document.id not in selected:
            continue
        entry = manifest.get(document.id)
        chunks = chunk_document(document, entry.short_name)
        vectors = embedder.embed_documents([c.content for c in chunks])
        name = artifact_filename(document.id, embedder.model, embedder.dimension)
        artifact = save_vectors(
            embeddings_dir / name,
            [c.provision_id for c in chunks],
            vectors,
            model=embedder.model,
            corpus_sha256=document.source_sha256,
        )
        if record:
            entry.embeddings = [a for a in entry.embeddings if a.model != artifact.model]
            entry.embeddings.append(artifact)
        else:
            write_sidecar(embeddings_dir, artifact)
        typer.echo(f"{document.id}: {len(chunks)} vectors -> {name}")
    if record:
        manifest.dump(_manifest_path(settings))


@model_app.command("fetch")
def model_fetch() -> None:
    """Download the local models (query embedder, reranker) at their pinned revisions,
    verifying every SHA-256."""
    settings = _settings()
    names = [settings.query_embedder, *([settings.reranker] if settings.reranker else [])]
    with httpx.Client(timeout=httpx.Timeout(60, read=600)) as client:
        for name in names:
            lock = load_lock(name)
            fetched = fetch_model(lock, settings.models_dir / name, client)
            typer.echo(
                f"{lock.repo}@{lock.revision[:12]}: {len(fetched)} file(s) fetched, all verified"
            )


@app.command()
def ingest(
    mode: Annotated[
        IngestMode | None, typer.Option(help="Where document vectors come from.")
    ] = None,
) -> None:
    """Load the corpus and its vectors into PostgreSQL."""
    settings = _settings()
    mode = mode or settings.ingest_mode
    manifest = Manifest.load(_manifest_path(settings))
    documents = load_documents(settings.corpus_dir, manifest)
    if not documents:
        raise typer.BadParameter("no built documents; run `base-legal corpus build` first")

    fallback: Embedder | None
    if mode is IngestMode.API:
        fallback = make_api_document_embedder(settings)
    elif mode is IngestMode.LOCAL:
        fallback = make_local_document_embedder(settings)
    elif mode is IngestMode.AUTO:
        use_api = settings.voyage_api_key is not None
        if use_api and importlib.util.find_spec("voyageai") is None:
            typer.echo(
                "VOYAGE_API_KEY is set but the voyage extra is not installed; embedding locally",
                err=True,
            )
            use_api = False
        fallback = (
            make_api_document_embedder(settings)
            if use_api
            else make_local_document_embedder(settings)
        )
    else:
        fallback = None

    store = Store.connect(settings.database_url)
    try:
        store.init_schema()
        reports = ingest_documents(
            store,
            documents,
            manifest,
            embeddings_dir=settings.corpus_dir / "embeddings",
            mode=mode,
            precomputed_model=settings.document_embedder,
            document_embedder=fallback,
            histories=load_histories(settings.corpus_dir, [d.id for d in documents]),
        )
    finally:
        store.close()
    for r in reports:
        source = "precomputed" if r.precomputed else "embedded"
        state = "unchanged" if r.skipped else "ingested"
        typer.echo(f"{r.document_id}: {r.chunks} chunks, {r.embedding_model} ({source}), {state}")


def _require_index(store: Store) -> None:
    if store.count_chunks() == 0:
        typer.echo("The index is empty: run `base-legal ingest` first.", err=True)
        raise typer.Exit(1)


@app.command()
def search(
    question: Annotated[str, typer.Argument(help="Question in Portuguese.")],
    k: Annotated[int, typer.Option("-k", min=1, max=50)] = 8,
) -> None:
    """Retrieve the most relevant provisions (no LLM involved)."""
    settings = _settings()
    redacted = redact(question)
    if redacted.total:
        typer.echo(f"[privacy] redacted {redacted.counts} before search", err=True)
    store = open_store(settings)
    try:
        _require_index(store)
        result = make_retriever(settings, store).search(redacted.text, k=k)
    finally:
        store.close()
    for ref in result.missing_references:
        typer.echo(f"! {ref} does not exist in the corpus")
    for n, hit in enumerate(result.hits, start=1):
        p = hit.provision
        marker = "=" if hit.explicit else " "
        typer.echo(f"{n:>2}{marker} {p.id:<28} {hit.score:.4f}  {' > '.join(p.path)}")
        typer.echo(f"     {p.text[:160]}")


def render_answer(answer: Answer) -> str:
    lines: list[str] = []
    if answer.status is Status.ANSWERED:
        numbers = {p.id: n for n, p in enumerate(answer.provisions, start=1)}
        text = "".join(
            part.text
            + "".join(
                f" [{numbers[c.provision_id]}]" for c in part.citations if c.provision_id in numbers
            )
            for part in answer.parts
        )
        lines += [text.strip(), "", "Fontes (texto oficial):"]
        lines += [f"[{numbers[p.id]}] {p.id} — {p.path}\n    {p.text}" for p in answer.provisions]
    else:
        lines.append(f"Sem base no corpus: {answer.message}")
        lines += [f"  ! {ref} não existe no corpus" for ref in answer.missing_references]
        if answer.provisions:
            lines += ["", "Dispositivos mais próximos (texto oficial):"]
            lines += [f"- {p.id} — {p.path}\n    {p.text}" for p in answer.provisions]
    lines += ["", answer.disclaimer]
    return "\n".join(lines)


@app.command()
def ask(question: Annotated[str, typer.Argument(help="Question in Portuguese.")]) -> None:
    """Answer with Claude, citing verified provisions, or refuse (PII redacted first)."""
    settings = _settings()
    store = open_store(settings)
    try:
        _require_index(store)
        answer = make_answerer(settings, store).answer(question)
    except GenerationUnavailableError as error:
        typer.echo(f"Claude API unavailable: {error}", err=True)
        raise typer.Exit(2) from None
    finally:
        store.close()
    if answer.redactions:
        typer.echo(f"[privacy] redacted {answer.redactions} before any third-party call", err=True)
    typer.echo(render_answer(answer))


@app.command()
def serve(
    host: Annotated[
        str, typer.Option(help="Bind address. Keep 127.0.0.1 unless behind a reverse proxy.")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
) -> None:
    """Run the HTTP API and the local web UI."""
    import uvicorn

    from base_legal.api.app import create_app
    from base_legal.wiring import DatabaseBackend

    settings = _settings()
    backend = DatabaseBackend(settings)
    try:
        # No uvicorn access log: it records client IPs (docs/PRIVACY.md); the app
        # logs method, path, status and timing only.
        uvicorn.run(create_app(backend, settings), host=host, port=port, access_log=False)
    finally:
        backend.close()


@app.command("mcp")
def mcp_server() -> None:
    """Run the read-only MCP server on stdio (for Claude Desktop / Claude Code)."""
    from base_legal.mcp_server.server import main as run_mcp

    run_mcp()


@eval_app.command("generation")
def eval_generation(
    golden_path: Annotated[Path, typer.Option("--golden")] = Path("evals/golden.yaml"),
    split: Annotated[Split, typer.Option()] = Split.DEV,
    limit: Annotated[
        int | None, typer.Option(min=1, help="Evaluate the first N items only.")
    ] = None,
    out_dir: Annotated[Path, typer.Option()] = Path("reports"),
    label: Annotated[str | None, typer.Option(help="Default: the model ID.")] = None,
    yes: Annotated[
        bool, typer.Option("--yes", help="Confirm: this calls the Claude API and costs money.")
    ] = False,
) -> None:
    """Answer the golden questions with Claude (paid, never in CI) -> JSON + Markdown."""
    if not yes:
        typer.echo("This calls the Claude API for every item; re-run with --yes.", err=True)
        raise typer.Exit(2)
    from base_legal.evals.generation import evaluate_generation
    from base_legal.evals.generation import to_markdown as generation_markdown

    settings = _settings()
    golden = GoldenSet.load(golden_path)
    store = open_store(settings)
    try:
        _require_index(store)
        answerer = make_answerer(settings, store)
        try:
            report = evaluate_generation(
                answerer,
                golden,
                split=split,
                model=settings.model,
                label=label or settings.model,
                limit=limit,
            )
        except GenerationUnavailableError as error:
            typer.echo(f"Claude API unavailable: {error}", err=True)
            raise typer.Exit(2) from None
    finally:
        store.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"generation-{report.label}-{split.value}"
    stem.with_suffix(".json").write_text(report.model_dump_json(indent=2) + "\n", "utf-8")
    markdown = generation_markdown(report)
    stem.with_suffix(".md").write_text(markdown, "utf-8")
    typer.echo(markdown)


@eval_app.command("retrieval")
def eval_retrieval(
    golden_path: Annotated[Path, typer.Option("--golden")] = Path("evals/golden.yaml"),
    split: Annotated[Split, typer.Option(help="dev to tune, holdout to confirm.")] = Split.DEV,
    mode: Annotated[SearchMode, typer.Option()] = SearchMode.HYBRID,
    threshold: Annotated[
        float | None, typer.Option(help="Refusal threshold (default: settings).")
    ] = None,
    out_dir: Annotated[Path, typer.Option()] = Path("reports"),
    label: Annotated[str, typer.Option(help="Name of this configuration.")] = "current",
    badge_path: Annotated[
        Path | None, typer.Option("--badge", help="Write a shields.io badge (recall@5).")
    ] = None,
    min_recall_at_5: Annotated[
        float | None, typer.Option(help="Fail (exit 1) below this recall@5 (0-1).")
    ] = None,
    min_refusal_accuracy: Annotated[
        float | None, typer.Option(help="Fail (exit 1) below this refusal accuracy (0-1).")
    ] = None,
) -> None:
    """Recall@k, MRR, refusal accuracy and latency on the golden set -> JSON + Markdown."""
    settings = _settings()
    golden = GoldenSet.load(golden_path)
    threshold = settings.refusal_threshold if threshold is None else threshold
    store = open_store(settings)
    try:
        _require_index(store)
        expected = sorted({pid for item in golden.answerable for pid in item.expected})
        unknown = golden.unknown_ids(store.provisions(expected))
        if unknown:
            raise typer.BadParameter(f"golden set cites provisions not in the index: {unknown}")
        retriever = make_retriever(settings, store, mode=mode)
        embedder = retriever.embedder
        report = evaluate(
            retriever,
            golden,
            split=split,
            threshold=threshold,
            label=label,
            config={
                "mode": mode.value,
                "query_embedder": embedder.model if embedder else "none",
                "document_embedder": store.document_embedding_models() or "none",
                "reranker": f"{settings.reranker} (depth {settings.rerank_depth})"
                if settings.reranker and retriever.reranker is not None
                else "none",
                **{k: str(v) for k, v in dataclasses.asdict(settings.tuning()).items()},
            },
        )
    finally:
        store.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"retrieval-{label}-{split.value}"
    stem.with_suffix(".json").write_text(report.model_dump_json(indent=2) + "\n", "utf-8")
    markdown = to_markdown(report)
    stem.with_suffix(".md").write_text(markdown, "utf-8")
    typer.echo(markdown)
    metrics = report.metrics
    if badge_path is not None:
        write_badge(badge_path, "recall@5", metrics.recall_at_5, good=0.65, fair=0.5)
    failures = []
    if min_recall_at_5 is not None and metrics.recall_at_5 < min_recall_at_5:
        failures.append(f"recall@5 {metrics.recall_at_5:.3f} < {min_recall_at_5}")
    accuracy = metrics.refusal_accuracy
    if min_refusal_accuracy is not None and (accuracy is None or accuracy < min_refusal_accuracy):
        failures.append(f"refusal accuracy {accuracy} < {min_refusal_accuracy}")
    if failures:
        typer.echo("Eval gate failed: " + "; ".join(failures), err=True)
        raise typer.Exit(1)


@eval_app.command("redteam")
def eval_redteam(
    cases_path: Annotated[Path, typer.Option("--cases")] = Path("evals/redteam.yaml"),
    out_dir: Annotated[Path, typer.Option()] = Path("reports"),
    with_index: Annotated[
        bool, typer.Option(help="Run retrieval-refusal checks against DATABASE_URL.")
    ] = True,
    seed: Annotated[int | None, typer.Option(help="Seed for synthetic test data.")] = None,
    badge_path: Annotated[
        Path | None, typer.Option("--badge", help="Write a shields.io badge (pass rate).")
    ] = None,
    min_pass_rate: Annotated[float, typer.Option(help="Fail (exit 1) below this rate.")] = 1.0,
) -> None:
    """Deterministic red-team checks: redaction, validator, refusal, isolation, limits, UI."""
    settings = _settings()
    cases = RedTeamSet.load(cases_path).cases
    manifest = Manifest.load(_manifest_path(settings))
    corpus = {p.id: p for d in load_documents(settings.corpus_dir, manifest) for p in d.provisions}
    store = open_store(settings) if with_index else None
    try:
        searcher = make_retriever(settings, store) if store is not None else None
        report = run_redteam(
            cases, corpus, searcher=searcher, threshold=settings.refusal_threshold, seed=seed
        )
    finally:
        if store is not None:
            store.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "redteam.json").write_text(report.model_dump_json(indent=2) + "\n", "utf-8")
    markdown = redteam_markdown(report, cases)
    (out_dir / "redteam.md").write_text(markdown, "utf-8")
    typer.echo(markdown)
    if badge_path is not None:
        write_badge(badge_path, "red-team", report.pass_rate, good=1.0, fair=0.9)
    if report.pass_rate < min_pass_rate:
        typer.echo(f"Red-team gate failed: pass rate {report.pass_rate:.3f}", err=True)
        raise typer.Exit(1)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    app()
