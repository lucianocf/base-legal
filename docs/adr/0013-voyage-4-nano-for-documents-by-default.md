# 0013. voyage-4-nano for documents by default (embedding gate result)

- Status: Proposed
- Date: 2026-09-27
- Supersedes: the document-embedding choice of ADR 0003 (B1 as primary)

## Context
ADR 0003 made `voyage-4-large` (API) for documents with `voyage-4-nano`
(local) for questions the primary configuration (B1), and set a gate:
"adopt B1 unless B3 beats it on hybrid recall@5 by more than 3 points". The
gate ran on 2026-09-27 over the full corpus (LGPD + six CD/ANPD resolutions,
1,281 chunks) and the golden set (45 answerable questions: 31 dev, 14
holdout). Full results: [docs/evals/embedding-gate.md](../evals/embedding-gate.md).

Hybrid recall@5 over all answerable questions, with the shipped retrieval
knobs (which were tuned on dev for B2):

| Config | Documents / questions | recall@5 | MRR | p50 per query (CPU) |
|---|---|---|---|---|
| B0 | full-text only | 32.2 % | 0.272 | 6 ms |
| B1 | voyage-4-large / voyage-4-nano | 58.9 % | 0.422 | 137 ms |
| **B2** | **voyage-4-nano / voyage-4-nano** | **67.8 %** | **0.449** | **132 ms** |
| B3 | Qwen3-Embedding-0.6B | 65.6 % | 0.417 | 537 ms |
| B4 | BGE-M3 (dense) | 58.9 % | 0.426 | 144 ms |

The knobs favour B2, so the same dev-only grid was re-run for each other
model and its best dev setting confirmed once on holdout: B1 reaches 62.9 %
dev / 57.8 % all, B3 64.5 % dev / 65.6 % all (MRR 0.582), B4 61.3 % dev /
61.1 % all. B2 stays first on recall@5 in both comparisons.

The literal ADR 0003 rule fires (B3 beats B1 by 6.7 points), but the rule
assumed B1 would be the strongest Voyage configuration. It is not: the
asymmetric setup is the weakest dense option here, below the symmetric nano
configuration the rule never considered as a winner.

## Decision
- **B2 is the primary configuration.** The default ingest mode becomes
  `local`: documents and questions are both embedded in-process with the
  pinned `voyage-4-nano` (ADR 0012). A default installation needs no Voyage
  key and makes no Voyage call.
- `api`, `precomputed` and `auto` stay available as opt-in modes
  (`BASE_LEGAL_INGEST_MODE`), unchanged. The refusal threshold (0.40) is
  calibrated on nano-to-nano similarities; deployers who switch to
  `voyage-4-large` document vectors should re-calibrate it.
- **B3 is not adopted.** Against B2 it is 2.2 points lower on recall@5 and
  about four times slower per query on CPU, and it would add a second
  pinned model. Its clear MRR advantage when tuned (0.582 against 0.449)
  is recorded as an open question for when the golden set is validated and
  larger, together with local reranking (ADR 0003, Phase 2).
- CI and the published evals already run in `local` mode, so they now
  measure exactly what ships.

## Consequences
- ➕ Best measured retrieval, and the evals measure the default
  configuration.
- ➕ Voyage leaves the default data flow entirely. It remains a third party
  only for maintainers or deployers who opt into `api` mode, and only for
  public law text; questions still never reach it.
- ➕ ADR 0009 (vector redistribution) no longer blocks a key-free
  quickstart.
- ➖ The golden set is small, synthetic and not yet validated by a DPO:
  45 answerable questions, so one question can move recall@5 by about 2
  points. B2 and B3 are within noise of each other on recall@5. Re-run
  the gate when the golden set grows.
- ➖ Ingestion embeds 1,281 chunks on CPU (minutes, once per corpus
  snapshot) instead of downloading precomputed vectors.
