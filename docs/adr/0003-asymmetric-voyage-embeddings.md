# 0003. Asymmetric Voyage 4 embeddings: API for the law, local model for questions

- Status: Proposed (revised 2026-09-26 after embedding research)
- Date: 2026-09-26

## Context
Anthropic does not offer an embeddings API. The first draft of this ADR
used the Voyage API for both documents and questions. Research showed a
better option. Facts checked on 2026-09-26:

- **Voyage 4 family:** `voyage-4-large`, `voyage-4`, `voyage-4-lite` (API) and
  **`voyage-4-nano`** (open weights, **Apache 2.0**, ~340M parameters). All
  four **share one embedding space**, so vectors from different members can be
  compared directly. Voyage recommends embedding documents with the large
  model and queries with a small one. Dimensions: 2048 / 1024 / 512 / 256;
  context: 32K.
- **Voyage data terms:** customer content may be used for training unless the
  org opts out; the opt-out needs a payment method and may void the free
  allowance (200M tokens for voyage-4 models).
- **Portuguese benchmarks:**
  - MTEB-BR (2026): an open-weight model (Qwen3-Embedding-8B, Apache 2.0)
    ties the top commercial APIs on Brazilian Portuguese.
  - JUÁ (2026, Brazilian legal IR): **BM25 stays highly competitive**, and is
    the strongest first stage on JurisTCU. This reinforces hybrid search
    (ADR 0004).
- `voyage-4-nano` has few independent benchmarks so far. Voyage reports it on
  par with `voyage-4-lite`.

Alternatives considered: Gemini Embedding (top MTEB-BR score, but another
processor receiving questions; its free tier trains on data); OpenAI
text-embedding-3-large (older model; closed models get deprecated, which
forces re-embedding); Cohere Embed v4 (trains by default); EmbeddingGemma
(Gemma terms extend to outputs, which is friction for an Apache-2.0 project);
BGE-M3 (MIT, dense + sparse, older); jua-4B-mixed (a Brazilian legal
specialist tuned mostly on case law, license unconfirmed, too heavy for CPU);
Qwen3-Embedding-0.6B (strong, Apache 2.0, fully local; kept as plan B).

## Decision
1. **Law → `voyage-4-large` via the API, once per corpus snapshot**
   (`input_type="document"`, 1024 dimensions). Only public legal text is
   sent, with no personal data, so Voyage's training default is not a
   privacy issue and **the opt-out is optional**. The corpus (a few hundred
   thousand tokens) fits the free allowance.
2. **Questions → `voyage-4-nano` running locally**, in-process on CPU
   (`input_type="query"`, 1024 dimensions). **User questions never leave the
   machine for embedding**, so Voyage is not a processor of user data.
3. **Deterministic, secret-free CI:** the nano model runs on the CI runner.
   The planned `evals/cache/` of query embeddings is no longer needed.
4. **Three ingestion modes**, chosen automatically:
   - `precomputed`: load the committed document vectors
     (`corpus/embeddings/`) if their hashes match the corpus snapshot. No key needed.
   - `api`: re-embed with `voyage-4-large` (maintainers; needs `VOYAGE_API_KEY`).
   - `local`: embed documents with `voyage-4-nano` too (fully offline; lower quality).
5. **Shared-space guard:** the index records the model per chunk; at startup
   the query embedder must belong to the same family and dimension, or the
   service refuses to start.
6. **Model supply chain:** nano weights pinned by Hugging Face revision
   (commit hash) and file SHA-256, safetensors only, downloaded **at image
   build time** (the runtime is offline). `trust_remote_code` is not allowed
   unless reviewed and pinned. **Verified 2026-09-26:** nano does need remote
   code (`modeling_qwen3_bidirectional.py`, 84 lines, torch/transformers only,
   no I/O). It was reviewed and pinned at revision `67fabc9`; every file's
   SHA-256 is in `src/base_legal/embeddings/voyage-4-nano.lock.json` and is
   re-verified on every load (`base-legal model fetch` downloads it). The code
   targets transformers 4.x, so the `local` extra pins `transformers<5`.
7. **Behind an `Embedder` protocol**, so plan B can be swapped in by configuration.

### Redistributing the precomputed vectors
Distributing the precomputed `voyage-4-large` vectors in the repo would mean
end users need **no Voyage key at all**. Checked 2026-09-27: Voyage's terms
(last updated 2026-05-27) are **silent** on outputs, so the vectors are not
committed until Voyage confirms in writing. Users run `api` mode once
(free tier) or `local` mode. See [ADR 0009](0009-no-redistribution-of-voyage-vectors-yet.md).

### Validation gate (Weekend 1, ~2 h)
Benchmark on the golden set before locking this in:

| Config | Documents | Questions |
|---|---|---|
| B0 | BM25 / FTS only | — |
| B1 | `voyage-4-large` | `voyage-4-nano` (**primary**) |
| B2 | `voyage-4-nano` | `voyage-4-nano` (`local` mode) |
| B3 | Qwen3-Embedding-0.6B | Qwen3-Embedding-0.6B (**plan B**) |
| B4 | BGE-M3 dense + sparse | BGE-M3 |

Each config runs both dense-only and hybrid with RRF. Metrics: recall@5,
MRR, CPU latency p50/p95 per query, image size. **Adopt B1 unless B3 beats
it on hybrid recall@5 by more than 3 points.** The results are published in
the docs and make good post material.

## Consequences
- ➕ Best-in-family document representations, and no third-party exposure of questions.
- ➕ Zero recurring cost and no training opt-out to manage.
- ➕ CI evals are deterministic and work on fork PRs without secrets.
- ➕ A possible quickstart with no Voyage key (pending terms).
- ➖ Adds a local model (~340M parameters) to the image and to CPU per query.
  Measured in the gate.
- ➖ Asymmetric quality is the vendor's claim until our benchmark confirms it.
- ➖ Tied to one model family's embedding space. Moving to plan B requires
  re-embedding the corpus (cheap at this scale).
- ➖ Reranking must also stay local to keep the property (Phase 2: a local
  cross-encoder such as Qwen3-Reranker-0.6B or bge-reranker-v2-m3, never a
  hosted reranker).
