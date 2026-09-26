# 0004. PostgreSQL + pgvector + FTS hybrid search with RRF

- Status: Proposed
- Date: 2026-09-26

## Context
Legal questions mix exact terms ("encarregado", "art. 48", "legítimo
interesse") with paraphrases ("who must I tell about a leak?"). Pure vector
search misses exact terms and article numbers; pure lexical search misses
paraphrases. The corpus is small (hundreds of provisions).

## Decision
- A single **PostgreSQL** instance with **pgvector** (HNSW index) and
  built-in **full-text search** (`portuguese` configuration + `unaccent`,
  GIN index).
- Run both searches and fuse the rankings with **Reciprocal Rank Fusion**
  (k = 60). Explicit references in the question ("art. 7, IX") are detected
  by regex and resolved as direct ID lookups ahead of the fused results.
- A **score threshold** under which the system refuses before generation
  (tuned on the golden set).

## Consequences
- ➕ One datastore for provisions, metadata and indexes, trivial to run with Docker Compose.
- ➕ Transparent and testable fusion logic.
- ➖ Postgres `ts_rank_cd` is **not true BM25**. If evals show lexical
  weakness, ParadeDB `pg_search` (real BM25 in Postgres) is the upgrade path,
  recorded here for honesty.
- ➖ A dedicated vector database is unnecessary at this scale; revisit only
  if the corpus grows by orders of magnitude.
