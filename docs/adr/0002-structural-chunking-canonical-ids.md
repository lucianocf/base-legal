# 0002. Structural chunking and canonical provision IDs

- Status: Proposed
- Date: 2026-09-26

## Context
Legal citations are hierarchical: article → paragraph → inciso → alínea →
item. Fixed-size or semantic chunking splits provisions arbitrarily and
makes exact citation impossible. Answers must cite down to the inciso, and a
validator must be able to check each citation mechanically.

## Decision
- The parser builds a **provision tree** per document. **One chunk per
  provision node**, at the finest level that carries normative text. The
  caput is its own node.
- Each chunk's embedded content is prefixed with its **hierarchy path**
  (e.g. `LGPD > Capítulo II > Seção I > Art. 7º > IX`). This is contextual
  retrieval done deterministically, with no LLM-generated context.
- Each node gets a **canonical, stable ID**:
  `{doc}:{art}[:{par}][:{inc}][:{ali}][:{item}]`, for example
  `lgpd:art11:incII:alig` (see ARCHITECTURE.md §4). IDs are part of the public API.
- Revoked text (struck through in the Planalto compiled version) is excluded
  from the in-force text. Amendment notes ("Redação dada pela Lei nº …") are
  kept as metadata.

## Consequences
- ➕ Exact, verifiable citations; stable deep links; a golden set that can be
  expressed as expected IDs.
- ➕ No LLM cost or nondeterminism at indexing time.
- ➖ A parent-level question ("what does art. 7 say?") needs the retriever to
  pull the caput plus its children. Handled by expanding to siblings and
  parents at query time.
- ➖ The parser is the riskiest component (irregular HTML). It is built
  test-first with fixtures of the hardest articles.
