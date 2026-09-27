"""One chunk per provision, with deterministic context (ADR 0002).

The embedded content is the hierarchy path plus the text of the provision's
ancestors (e.g. the article caput "considera-se:" above an inciso) and the
provision itself. This is contextual retrieval without an LLM: no generated
text ever enters the index.
"""

from __future__ import annotations

from dataclasses import dataclass

from base_legal.corpus.models import Document, Provision

MAX_ANCESTOR_CHARS = 300


@dataclass(frozen=True, slots=True)
class Chunk:
    provision_id: str
    document_id: str
    content: str


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def chunk_document(document: Document, short_name: str) -> list[Chunk]:
    """Build chunks for every provision in force that has text of its own."""
    by_id = document.by_id()
    chunks: list[Chunk] = []
    for provision in document.in_force():
        if not provision.text:
            continue
        chunks.append(
            Chunk(
                provision_id=provision.id,
                document_id=document.id,
                content=_content(provision, by_id, short_name),
            )
        )
    return chunks


def _content(provision: Provision, by_id: dict[str, Provision], short_name: str) -> str:
    ancestors: list[str] = []
    parent_id = provision.parent_id
    while parent_id is not None:
        parent = by_id[parent_id]
        if parent.text:
            ancestors.append(_clip(parent.text, MAX_ANCESTOR_CHARS))
        parent_id = parent.parent_id
    header = " > ".join((short_name, *provision.path))
    return "\n".join([header, *reversed(ancestors), provision.text])
