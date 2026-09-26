# 0003. Embeddings via Voyage behind a pluggable interface

- Status: Proposed
- Date: 2026-09-26

## Context
Anthropic does not offer an embeddings API. The options were a local
open-source model (BGE-M3, multilingual-e5), which is private, free and
deterministic but brings a heavy image and slower CPU inference, or Voyage
AI, which offers high-quality multilingual models, a light setup and is the
partner Anthropic recommends. The author chose Voyage.

Facts checked on 2026-09-26 (to be re-checked at implementation):
- The `voyage-4` family is general purpose and multilingual, with a 32K
  context and output dimensions of 2048, 1024 (default), 512 and 256. The
  voyage-4 family shares one embedding space.
- There is a free allowance of 200M tokens per account for voyage-4 models.
  The voyage-3.x models no longer carry one.
- **By default, Voyage may use customer content to train its models.**
  Opting out gives zero-day retention, but requires a payment method and may
  void the free-token credits.

## Decision
- Use **`voyage-4` at 1024 dimensions** (`input_type="document"` for
  provisions, `"query"` for questions) behind an `Embedder` protocol, so a
  local model can be dropped in later.
- **Opting out of training is mandatory** and part of the setup checklist
  (PRIVACY.md §4).
- Only **redacted** questions are embedded.
- **CI determinism:** golden-set query embeddings are cached in
  `evals/cache/` (keyed by model + SHA-256 of the question), so fork PRs run
  retrieval evals without secrets or cost.

## Consequences
- ➕ High retrieval quality with a small Docker image; cheap for a corpus of
  a few hundred thousand tokens.
- ➖ One more processor receiving (redacted) questions, documented as an
  international transfer.
- ➖ The opt-out may cost the free tier, so the budget is a few cents rather
  than zero. `TODO(verify)` with current pricing.
- ➖ Changing the model requires re-embedding and regenerating the cache. The
  model name is stored per chunk to detect mismatches.
