# Embedding validation gate

Run on 2026-09-27 (ADR 0003). Decision: [ADR 0013](../adr/0013-voyage-4-nano-for-documents-by-default.md),
**voyage-4-nano for documents and questions (B2)**.

## Setup

- Corpus: LGPD + six CD/ANPD resolutions, 1,281 chunks. Each configuration
  is ingested into its own PostgreSQL schema.
- Golden set: 45 synthetic answerable questions (dev 31, holdout 14), not
  yet validated by a DPO. A single question can move recall@5 by up to about 2 points
  overall, 3 on dev and 7 on holdout.
- Questions are always embedded locally. Voyage only ever received public
  law text (`corpus embed`, maintainer run for B1).
- Retrieval knobs: the shipped ones (`BASE_LEGAL_FTS_NORMALIZATION=4`,
  lexical weight 0.5, parent weight 0.2), which were tuned on dev **for B2**.
  A second pass below tunes each model on dev on its own.
- Latency: time per question for query embedding plus search, on CPU. All
  configurations ran on the same machine with nothing else running.
  Absolute values depend on the hardware; compare them relative to each
  other.

## Results with the shipped knobs

| Config | Documents | Questions | Mode | recall@5 dev | recall@5 holdout | recall@5 all | MRR all | p50 / p95 |
|---|---|---|---|---|---|---|---|---|
| B0 | none (full-text only) | none | lexical | 35.5 % | 25.0 % | 32.2 % | 0.272 | 6 / 12 ms |
| B1 | voyage-4-large (API) | voyage-4-nano (local) | dense | 50.0 % | 53.6 % | 51.1 % | 0.368 | 127 / 162 ms |
| B1 | voyage-4-large (API) | voyage-4-nano (local) | hybrid | 61.3 % | 53.6 % | 58.9 % | 0.422 | 137 / 177 ms |
| B2 | voyage-4-nano (local) | voyage-4-nano (local) | dense | 56.5 % | 53.6 % | 55.6 % | 0.403 | 131 / 166 ms |
| **B2** | **voyage-4-nano (local)** | **voyage-4-nano (local)** | **hybrid** | **67.7 %** | **67.9 %** | **67.8 %** | **0.449** | **132 / 152 ms** |
| B3 | Qwen3-Embedding-0.6B | Qwen3-Embedding-0.6B | dense | 45.2 % | 53.6 % | 47.8 % | 0.395 | 524 / 652 ms |
| B3 | Qwen3-Embedding-0.6B | Qwen3-Embedding-0.6B | hybrid | 61.3 % | 75.0 % | 65.6 % | 0.417 | 537 / 640 ms |
| B4 | BGE-M3 (dense) | BGE-M3 (dense) | dense | 48.4 % | 53.6 % | 50.0 % | 0.357 | 135 / 204 ms |
| B4 | BGE-M3 (dense) | BGE-M3 (dense) | hybrid | 58.1 % | 60.7 % | 58.9 % | 0.426 | 144 / 228 ms |

BGE-M3 was run dense-only. Its sparse output is not used, since PostgreSQL
full-text search already provides the lexical side.

## Each model tuned on its own

The same 60-combination grid (`benchmarks/tune_retrieval.py`, dev only) was
run for each model. Each model's best dev setting was then evaluated once on
holdout (hybrid mode):

| Config | Best dev knobs (normalization, lexical, parent) | recall@5 dev | recall@5 holdout | recall@5 all | MRR all |
|---|---|---|---|---|---|
| B1 | 4, 1.0, 0.2 | 62.9 % | 46.4 % | 57.8 % | 0.389 |
| **B2** | **4, 0.5, 0.2** (shipped) | **67.7 %** | **67.9 %** | **67.8 %** | **0.449** |
| B3 | 2, 1.0, 0.0 | 64.5 % | 67.9 % | 65.6 % | 0.582 |
| B4 | 2, 1.0, 0.2 | 61.3 % | 60.7 % | 61.1 % | 0.434 |

## Model weights

| Model | Size on disk | In the image |
|---|---|---|
| voyage-4-nano | 672 MB | Yes (already needed for questions) |
| Qwen3-Embedding-0.6B | 1.2 GB | No (benchmark only) |
| BGE-M3 | 2.2 GB | No (benchmark only) |

## Verdict

- **ADR 0003 rule** ("adopt B1 unless B3 beats it on hybrid recall@5 by more
  than 3 points"): B3 − B1 = **+6.7 points**, so the rule fires against B1.
  It does not cover the actual winner: the asymmetric B1 is the weakest
  dense option on this corpus, even after tuning its own knobs.
- **B2 is first on recall@5** with the shipped knobs and with each model
  tuned on its own. It is also as fast as any dense option and needs no API
  key and no extra model.
- **B3** trails B2 by 2.2 points of recall@5, which is within noise on 45
  questions. When tuned, its MRR is clearly better (0.582 against 0.449),
  but it is about four times slower per question and adds a 1.2 GB model.
  It is not adopted now; re-run the gate once the golden set is validated
  and has grown.
- Decision: **B2**, recorded in [ADR 0013](../adr/0013-voyage-4-nano-for-documents-by-default.md).
  `local` is now the default ingest mode, and it is what CI and the published
  evals measure.

## Reproduce

```bash
uv sync --extra local --extra voyage --extra bench
export DATABASE_URL=postgresql://...        # a scratch database
uv run base-legal corpus embed              # B1 only: needs VOYAGE_API_KEY (public law text)
uv run python benchmarks/embedding_gate.py --configs B0,B1,B2,B3,B4
uv run python benchmarks/embedding_gate.py --configs B0,B1,B2,B3,B4 --no-ingest   # timing pass
uv run python benchmarks/tune_retrieval.py --schema gate_b3 --query-model qwen3-embedding-0.6b
uv run python benchmarks/gate_report.py
```
