# 0015. A local cross-encoder reranker, blended with hybrid retrieval

- Status: Proposed
- Date: 2026-09-27

## Context
ADR 0003 left reranking for Phase 2, "only if the golden set shows a gain",
and only with a **local** model: a hosted reranker would send questions to a
third party. Adding the LAI (Phase 2) lowered holdout recall@5 from 67.9 %
to 58.3 %. Its provisions compete with the LGPD's for words like "necessidade"
and "informação". On a single document the top 5 was often one cluster
(the dosimetry regulation, LAI art. 8).

`benchmarks/rerank.py` reranked the hybrid top-N with three pinned,
Apache-2.0 models. Each ran locally from safetensors with no remote code.
Two variants were tested: the reranker's order alone, and a **blend** (RRF of
the hybrid order and the reranker's order). Golden set of 2026-09-27: 41 dev
and 18 holdout answerable questions. Latency is the rerank step alone, on CPU.

Blended recall@5:

| Model | Depth | dev | holdout | all | MRR all | p50 |
|---|---|---|---|---|---|---|
| none (hybrid only) | | 68.3 % | 58.3 % | 65.3 % | 0.433 | |
| mMiniLMv2-L12 (118M) | 20 | 68.3 % | 72.2 % | 69.5 % | 0.577 | 0.45 s |
| **mMiniLMv2-L12 (118M)** | **10** | **75.6 %** | **66.7 %** | **72.9 %** | **0.563** | **0.20 s** |
| bge-reranker-v2-m3 (568M) | 20 | 65.9 % | 72.2 % | 67.8 % | 0.575 | 5.5 s |
| Qwen3-Reranker-0.6B | 20 | 74.4 % | 69.4 % | 72.9 % | 0.587 | 5.9 s |
| Qwen3-Reranker-0.6B | 10 | 72.0 % | 69.4 % | 71.2 % | 0.580 | 2.5 s |

The reranker's order alone was worse than the blend on dev for every model.

## Decision
- Rerank the **top 10** of the hybrid ranking with
  **cross-encoder/mmarco-mMiniLMv2-L12-H384-v1** and blend the two orders with
  RRF (k = 60, equal weights, ties keep the hybrid order). Explicit references
  stay first. The dense-similarity refusal threshold is unchanged.
- The choice follows dev, where it is best (+7.3 points). Holdout confirms a
  gain (+8.4 points). It costs about 0.2 s per question on CPU, against
  2.5–6 s for the larger models.
- The weights are pinned by revision and SHA-256, like voyage-4-nano
  (`src/base_legal/embeddings/mmarco-mminilmv2.lock.json`):
  - `base-legal model fetch` downloads them, and the image fetches them at
    build time;
  - they are verified again on every load;
  - they run on transformers directly, with no sentence-transformers or
    remote code at runtime;
  - `tests/integration/test_reranker.py` checks the scores against the
    reference CrossEncoder.
- `BASE_LEGAL_RERANKER=none` disables it; `BASE_LEGAL_RERANK_DEPTH` sets
  the depth. The CI eval gate rises to recall@5 ≥ 0.70.

## Consequences
- ➕ recall@5 72.9 % and MRR 0.563 over all questions, up from 65.2 % and
  0.426. Questions still never leave the machine.
- ➕ The best candidate comes first more often (MRR), which matters for the
  generation prompt.
- ➖ +470 MB of weights in the image and about 0.2 s per question.
- ➖ The reranker's scores do not separate out-of-corpus questions, so
  refusal is not improved: 66.7 % of the must-refuse questions are refused.
  Qwen3-Reranker's scores did (3 of 5 out-of-corpus questions below every
  answerable one). It is the candidate if refusal becomes the priority and
  2.5 s per question is acceptable.
- ➖ 41 dev questions: depth 10 against depth 20 is within noise. Re-run
  `benchmarks/rerank.py` when the golden set grows.
