"""PostgreSQL storage: schema, idempotent ingestion and the two first-stage searches.

Full-text search uses the ``portuguese`` configuration on accent-folded text
(folding is done in Python, so no ``unaccent`` extension is required). It is
Postgres ``ts_rank_cd``, not true BM25 (ADR 0004).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from base_legal.chunking.chunker import Chunk
from base_legal.corpus.models import Document, Provision
from base_legal.embeddings.base import EMBEDDING_DIM, Vectors

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id                   text PRIMARY KEY,
    title                text NOT NULL,
    kind                 text NOT NULL,
    source_url           text NOT NULL,
    retrieved_at         date NOT NULL,
    source_sha256        text NOT NULL,
    redistribution_basis text NOT NULL,
    embedding_model      text NOT NULL
);

CREATE TABLE IF NOT EXISTS provisions (
    id          text PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    parent_id   text REFERENCES provisions (id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    kind        text NOT NULL,
    label       text NOT NULL,
    path        text[] NOT NULL,
    text        text NOT NULL,
    amendments  text[] NOT NULL DEFAULT '{{}}',
    revoked     boolean NOT NULL DEFAULT false,
    vetoed      boolean NOT NULL DEFAULT false,
    ordinal     integer NOT NULL,
    valid_from  date,
    valid_to    date
);

CREATE TABLE IF NOT EXISTS chunks (
    provision_id    text PRIMARY KEY REFERENCES provisions (id) ON DELETE CASCADE,
    content         text NOT NULL,
    fts             tsvector NOT NULL,
    embedding       vector({EMBEDDING_DIM}) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING gin (fts);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS index_meta (
    key   text PRIMARY KEY,
    value text NOT NULL
);
"""


def fold(text: str) -> str:
    """Lowercase and strip diacritics, for accent-insensitive full-text search."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def or_query(text: str) -> str | None:
    """Build an OR ``to_tsquery`` from alphanumeric tokens (no operator injection)."""
    tokens = [t for t in re.findall(r"[a-z0-9]+", fold(text)) if len(t) > 1]
    return " | ".join(dict.fromkeys(tokens)) or None


@dataclass(frozen=True, slots=True)
class Ranked:
    provision_id: str
    score: float


class IndexMismatchError(RuntimeError):
    """The index was built with a different embedding space than configured."""


class Store:
    def __init__(self, conn: psycopg.Connection[dict[str, object]]) -> None:
        self.conn = conn

    @classmethod
    def connect(cls, database_url: str) -> Store:
        # Autocommit: reads never open a lingering transaction, and every
        # `with conn.transaction()` block is a real, committed transaction
        # (not a savepoint that `close()` would roll back).
        conn = psycopg.connect(database_url, row_factory=dict_row, autocommit=True)
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        return cls(conn)

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        with self.conn.transaction():
            self.conn.execute(SCHEMA.encode())

    # -- metadata ------------------------------------------------------------

    def get_meta(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM index_meta").fetchall()
        return {str(r["key"]): str(r["value"]) for r in rows}

    def set_meta(self, **values: str) -> None:
        with self.conn.transaction():
            for key, value in values.items():
                self.conn.execute(
                    "INSERT INTO index_meta (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (key, value),
                )

    def ensure_space(self, family: str, dimension: int) -> None:
        meta = self.get_meta()
        if not meta:
            self.set_meta(embedding_family=family, embedding_dim=str(dimension))
            return
        if meta.get("embedding_family") != family or meta.get("embedding_dim") != str(dimension):
            raise IndexMismatchError(
                f"index space is {meta.get('embedding_family')}/{meta.get('embedding_dim')}, "
                f"got {family}/{dimension}; drop the index to re-embed"
            )

    # -- ingestion -----------------------------------------------------------

    def is_current(self, document: Document, embedding_model: str) -> bool:
        row = self.conn.execute(
            "SELECT source_sha256, embedding_model FROM documents WHERE id = %s", (document.id,)
        ).fetchone()
        return (
            row is not None
            and row["source_sha256"] == document.source_sha256
            and row["embedding_model"] == embedding_model
        )

    def replace_document(
        self,
        document: Document,
        chunks: Sequence[Chunk],
        vectors: Vectors,
        embedding_model: str,
    ) -> None:
        """Atomically replace one document, its provisions and its chunks."""
        if len(chunks) != vectors.shape[0]:
            raise ValueError("chunks and vectors differ in length")
        with self.conn.transaction():
            self.conn.execute("DELETE FROM documents WHERE id = %s", (document.id,))
            self.conn.execute(
                "INSERT INTO documents (id, title, kind, source_url, retrieved_at, source_sha256,"
                " redistribution_basis, embedding_model) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    document.id,
                    document.title,
                    document.kind.value,
                    document.source_url,
                    document.retrieved_at,
                    document.source_sha256,
                    document.redistribution_basis,
                    embedding_model,
                ),
            )
            with self.conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO provisions (id, document_id, parent_id, kind, label, path, text,"
                    " amendments, revoked, vetoed, ordinal, valid_from, valid_to)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        (
                            p.id,
                            p.document_id,
                            p.parent_id,
                            p.kind.value,
                            p.label,
                            list(p.path),
                            p.text,
                            list(p.amendments),
                            p.revoked,
                            p.vetoed,
                            p.ordinal,
                            p.valid_from,
                            p.valid_to,
                        )
                        for p in document.provisions
                    ],
                )
                cur.executemany(
                    "INSERT INTO chunks (provision_id, content, fts, embedding)"
                    " VALUES (%s, %s, to_tsvector('portuguese', %s), %s)",
                    [
                        (c.provision_id, c.content, fold(c.content), vector)
                        for c, vector in zip(chunks, vectors, strict=True)
                    ],
                )

    # -- search --------------------------------------------------------------

    def lexical(self, question: str, limit: int, normalization: int = 0) -> list[Ranked]:
        """Full-text candidates. ``normalization`` is ``ts_rank_cd``'s bit mask
        (e.g. 1 divides by 1 + log(length), 2 by length); 0 favours long chunks."""
        query = or_query(question)
        if query is None:
            return []
        rows = self.conn.execute(
            "SELECT provision_id, ts_rank_cd(fts, q, %s) AS score"
            " FROM chunks, to_tsquery('portuguese', %s) AS q"
            " WHERE fts @@ q ORDER BY score DESC, provision_id LIMIT %s",
            (normalization, query, limit),
        ).fetchall()
        return [Ranked(str(r["provision_id"]), float(r["score"])) for r in rows]  # type: ignore[arg-type]

    def dense(self, query_vector: Vectors, limit: int) -> list[Ranked]:
        rows = self.conn.execute(
            "SELECT provision_id, 1 - (embedding <=> %s) AS score"
            " FROM chunks ORDER BY embedding <=> %s, provision_id LIMIT %s",
            (query_vector, query_vector, limit),
        ).fetchall()
        return [Ranked(str(r["provision_id"]), float(r["score"])) for r in rows]  # type: ignore[arg-type]

    def parents(self, ids: Sequence[str]) -> dict[str, str | None]:
        """``parent_id`` of each provision and of all its ancestors."""
        if not ids:
            return {}
        rows = self.conn.execute(
            "WITH RECURSIVE up AS ("
            " SELECT id, parent_id FROM provisions WHERE id = ANY(%s)"
            " UNION SELECT p.id, p.parent_id FROM provisions p JOIN up ON p.id = up.parent_id)"
            " SELECT id, parent_id FROM up",
            (list(ids),),
        ).fetchall()
        return {
            str(r["id"]): (None if r["parent_id"] is None else str(r["parent_id"])) for r in rows
        }

    def provisions(self, ids: Sequence[str]) -> dict[str, Provision]:
        if not ids:
            return {}
        rows = self.conn.execute(
            "SELECT * FROM provisions WHERE id = ANY(%s)", (list(ids),)
        ).fetchall()
        return {str(r["id"]): _row_to_provision(r) for r in rows}

    def normative_ids(self, ids: Sequence[str]) -> set[str]:
        """The subset of ``ids`` that exist and are in force (neither revoked nor vetoed)."""
        if not ids:
            return set()
        rows = self.conn.execute(
            "SELECT id FROM provisions WHERE id = ANY(%s) AND NOT revoked AND NOT vetoed",
            (list(ids),),
        ).fetchall()
        return {str(r["id"]) for r in rows}

    def annex_titles(self) -> list[tuple[str, str, str]]:
        """``(document_id, annex, title)`` of every annex, e.g. its regulation's name."""
        rows = self.conn.execute(
            "SELECT DISTINCT document_id, substring(id FROM ':anx([0-9]+):') AS annex,"
            " path[1] AS title FROM provisions WHERE id ~ ':anx[0-9]+:' ORDER BY 1, 2"
        ).fetchall()
        return [(str(r["document_id"]), str(r["annex"]), str(r["title"])) for r in rows]

    def document_embedding_models(self) -> str:
        """Comma-separated embedding models the indexed documents were embedded with."""
        rows = self.conn.execute(
            "SELECT DISTINCT embedding_model FROM documents ORDER BY embedding_model"
        ).fetchall()
        return ",".join(str(r["embedding_model"]) for r in rows)

    def count_chunks(self) -> int:
        row = self.conn.execute("SELECT count(*) AS n FROM chunks").fetchone()
        return int(row["n"]) if row else 0  # type: ignore[call-overload]


def _row_to_provision(row: dict[str, object]) -> Provision:
    return Provision.model_validate(row)
