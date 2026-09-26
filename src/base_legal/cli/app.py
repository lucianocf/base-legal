"""``base-legal`` command-line interface."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import httpx
import typer

from base_legal.chunking.chunker import chunk_document
from base_legal.config import IngestMode, Settings
from base_legal.corpus.manifest import Manifest
from base_legal.corpus.pipeline import build, fetch, load_documents, write_document
from base_legal.embeddings.base import Embedder, check_compatible
from base_legal.embeddings.factory import (
    make_api_document_embedder,
    make_local_document_embedder,
    make_query_embedder,
)
from base_legal.embeddings.model_store import fetch_model, load_lock
from base_legal.embeddings.precomputed import artifact_filename, save_vectors
from base_legal.ingest import ingest_documents
from base_legal.privacy.redact import redact
from base_legal.retrieval.search import Retriever
from base_legal.store.db import Store

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
corpus_app = typer.Typer(no_args_is_help=True, help="Maintain the normalized corpus.")
app.add_typer(corpus_app, name="corpus")
model_app = typer.Typer(no_args_is_help=True, help="Manage pinned local model weights.")
app.add_typer(model_app, name="model")

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


@corpus_app.command("build")
def corpus_build(doc: DocOption = None) -> None:
    """Parse raw sources into normalized JSON under the corpus directory."""
    settings = _settings()
    manifest = Manifest.load(_manifest_path(settings))
    for doc_id in _selected(manifest, doc):
        document = build(manifest.get(doc_id), settings.raw_dir)
        path = write_document(document, settings.corpus_dir)
        in_force = len(document.in_force())
        typer.echo(
            f"{doc_id}: {len(document.provisions)} provisions ({in_force} in force) -> {path}"
        )


@corpus_app.command("embed")
def corpus_embed(doc: DocOption = None) -> None:
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
        entry.embeddings = [a for a in entry.embeddings if a.model != artifact.model] + [artifact]
        typer.echo(f"{document.id}: {len(chunks)} vectors -> {name}")
    manifest.dump(_manifest_path(settings))


@model_app.command("fetch")
def model_fetch() -> None:
    """Download the local query model at its pinned revision, verifying every SHA-256."""
    settings = _settings()
    lock = load_lock(settings.query_embedder)
    directory = settings.models_dir / settings.query_embedder
    with httpx.Client(timeout=httpx.Timeout(60, read=600)) as client:
        fetched = fetch_model(lock, directory, client)
    typer.echo(f"{lock.repo}@{lock.revision[:12]}: {len(fetched)} file(s) fetched, all verified")


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
        fallback = (
            make_api_document_embedder(settings)
            if settings.voyage_api_key is not None
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
        )
    finally:
        store.close()
    for r in reports:
        source = "precomputed" if r.precomputed else "embedded"
        state = "unchanged" if r.skipped else "ingested"
        typer.echo(f"{r.document_id}: {r.chunks} chunks, {r.embedding_model} ({source}), {state}")


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
    embedder = make_query_embedder(settings)
    store = Store.connect(settings.database_url)
    try:
        meta = store.get_meta()
        if meta:
            check_compatible(meta["embedding_family"], int(meta["embedding_dim"]), embedder)
        result = Retriever(store, embedder, candidate_pool=settings.candidate_pool).search(
            redacted.text, k=k
        )
    finally:
        store.close()
    for ref in result.missing_references:
        typer.echo(f"! {ref} does not exist in the corpus")
    for n, hit in enumerate(result.hits, start=1):
        p = hit.provision
        marker = "=" if hit.explicit else " "
        typer.echo(f"{n:>2}{marker} {p.id:<28} {hit.score:.4f}  {' > '.join(p.path)}")
        typer.echo(f"     {p.text[:160]}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    app()
