# 0012. Load voyage-4-nano without remote code, on transformers 5.x

- Status: Proposed
- Date: 2026-09-27

## Context
ADR 0003 (decision 6) pinned `voyage-4-nano` at revision `67fabc9`, including
its remote code (`modeling_qwen3_bidirectional.py`, 84 lines, reviewed), and
pinned `transformers<5` because that code targets transformers 4.x.

On 2026-09-27, `pip-audit` on the locked set reported advisories against
transformers 4.57.6 that are fixed only in 5.x, including CVE-2026-4372
(GHSA-29pf-2h5f-8g72, fixed in 5.3.0) and CVE-2026-9856
(GHSA-xrqw-3rrv-vx5w, arbitrary file write, fixed in 5.10.0). Under
transformers 5.x the vendor's remote code no longer loads (its model class
lacks `config_class`), and the model repository has no newer revision.

The remote code is small: Qwen3 with the causal mask replaced by a
bidirectional (padding-only) mask, plus a linear head from the 1024-wide
hidden state to 2048 dimensions; sentence-transformers then mean-pools
(prompt included), normalizes and truncates to 1024 dimensions.

## Decision
- `base_legal.embeddings.nano` rebuilds that computation on transformers' own
  `Qwen3Model`: every layer non-causal, an explicit additive 4-D mask that
  hides only padding, the linear head, mean pooling over the attention mask,
  the first 1024 dimensions, L2 normalization, and the prompts read from the
  pinned `config_sentence_transformers.json`.
- **No code from the model repository is executed.** `trust_remote_code` is
  gone; the lock records `remote_code: null`. The `.py` file stays pinned by
  hash for completeness and is never imported.
- The `local` extra becomes `transformers>=5.10,<6` + `torch`.
  `sentence-transformers` moves to a `bench` extra used only by the
  benchmark-only models of the embedding gate (Qwen3-Embedding, BGE-M3).
- Equivalence was checked before switching: on three queries and three
  documents (batched with padding) the new encoder matches the vendor code
  running on transformers 4.57.6 with a maximum absolute difference of
  1.5e-8 (float32). `tests/integration/test_nano.py` keeps that check against
  reference vectors produced by the vendor code
  (`tests/fixtures/nano_reference.json`).
- CI audits the CPU-only torch wheel (`X.Y.Z+cpu`, not on PyPI) under its
  upstream version, since advisories are keyed by version.

## Consequences
- ➕ The transformers advisories are closed; `pip-audit --strict` passes.
- ➕ Less supply-chain surface: no remote code at all, and no
  sentence-transformers (with scikit-learn and scipy) in the runtime image.
- ➕ Embeddings are unchanged, so indexes and the retrieval tuning stay valid.
- ➖ About 60 lines of model code are ours to maintain across transformers
  releases. The reference test fails loudly if a release changes the
  numbers, and the evals workflow runs the encoder on every pull request.
- ➖ A future nano revision with different architecture code needs this
  module updated rather than a new remote-code review.
