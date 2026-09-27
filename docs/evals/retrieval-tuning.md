# Retrieval tuning (2026-09-27)

Configuration: full corpus (LGPD + 6 CD/ANPD resolutions, 1,281 chunks),
`local` mode (voyage-4-nano for documents and questions), hybrid search.
Tuning used the golden **dev** split only (31 answerable + 5 must-refuse);
the **holdout** split (14 + 3) was evaluated once per candidate, to confirm or
reject it. Golden items are synthetic and still unverified by a DPO.

## Hypotheses (from the baseline failures)

1. **OR full-text favors long chunks.** Queries are OR-ed terms, and
   `ts_rank_cd` without normalization rewards chunks that match many terms,
   i.e. long ones (LGPD art. 60, which quotes amendments to another law, matched
   almost everything).
2. **Missing parent/child expansion.** Chunks of incisos carry the caput of
   their article as context, so for parent-level questions ("quais são as
   hipóteses…", "quais são os direitos…") the children outrank the article
   itself.
3. **Uncalibrated refusal threshold.** Only nonexistent explicit references
   were refused.

## Knobs

| Knob | Values tried | Chosen |
|---|---|---|
| `ts_rank_cd` normalization (`BASE_LEGAL_FTS_NORMALIZATION`) | 0, 1, 2, 4, 32 | 4 |
| Full-text weight in RRF (`BASE_LEGAL_LEXICAL_WEIGHT`, dense = 1) | 0.5, 1.0, 1.5 | 0.5 |
| Share of a hit's score propagated to each ancestor, decaying by level (`BASE_LEGAL_PARENT_WEIGHT`) | 0, 0.2, 0.35, 0.5 | 0.2 |
| Refusal threshold on the best dense similarity (`BASE_LEGAL_REFUSAL_THRESHOLD`) | 0.47, 0.40 | 0.40 |

Grid: `benchmarks/tune_retrieval.py` (60 combinations, dev only).

## Dev results (selected rows)

| Normalization | Lexical weight | Parent weight | recall@5 | MRR | recall@10 |
|---|---|---|---|---|---|
| 0 | 1.0 | 0 | 33.9 % | 0.292 | 50.0 % |
| 0 | 1.0 | 0.2 | 58.1 % | 0.400 | 72.6 % |
| 2 | 1.0 | 0 | 62.9 % | 0.514 | 74.2 % |
| 2 | 0.5 | 0 | 62.9 % | 0.483 | 80.6 % |
| 4 | 0.5 | 0 | 48.4 % | 0.467 | 74.2 % |
| **4** | **0.5** | **0.2** | **67.7 %** | **0.474** | **79.0 %** |

Hypotheses 1 and 2 are confirmed: length normalization alone and ancestor
propagation alone each add about 25 points of dev recall@5. The knobs
interact strongly (normalization 4 needs propagation; normalization 2 does
worse with it), which on 31 questions is also a warning about noise: the
simpler configuration (normalization 2, no propagation) is within five points
and has a better MRR. The dev optimum was kept because it was chosen before
looking at holdout; re-running the grid when the golden set is validated and
grows is recommended.

## Refusal threshold

Best dense similarity on dev: lowest answerable 0.481; out-of-scope and
off-topic questions 0.204 to 0.464.

| Threshold | Split | Refusal accuracy | False refusals | recall@5 |
|---|---|---|---|---|
| none | holdout | 33.3 % | 0.0 % | 67.9 % |
| 0.47 (dev optimum) | holdout | 66.7 % | **14.3 %** | 53.6 % |
| **0.40** (dev minimum − 0.08) | holdout | 66.7 % | **0.0 %** | 67.9 % |

0.47 separated dev perfectly but overfitted a 0.017-wide gap; it was
rejected. 0.40 keeps a safety margin and was confirmed on holdout. Many
out-of-scope questions still pass retrieval (a GDPR question scores 0.62
against LGPD art. 52); generation refuses them (`SEM_BASE` and the citation
validator), which the deterministic evals cannot measure.

## Before and after

| Split | Metric | Baseline | Tuned |
|---|---|---|---|
| dev | recall@1 / @5 / @10 | 19.4 / 33.9 / 50.0 % | 27.4 / 67.7 / 79.0 % |
| dev | MRR | 0.292 | 0.474 |
| dev | refusal accuracy / false refusals | 40.0 % / 0 % | 60.0 % / 0 % |
| holdout | recall@1 / @5 / @10 | 21.4 / 42.9 / 67.9 % | 17.9 / 67.9 / 82.1 % |
| holdout | MRR | 0.326 | 0.393 |
| holdout | refusal accuracy / false refusals | 33.3 % / 0 % | 66.7 % / 0 % |

Holdout recall@1 fell slightly (one item). Known failures from the brief:
g43 ("vazamento… avisar a ANPD", expects `lgpd:art48`) went from not
retrieved to rank 2; g44 ("levar meus dados para outra empresa", expects
`lgpd:art18:incV`) improved to rank 8 but is still outside the top 5 (the
question pulls towards international transfer).

Latency is dominated by the local query embedding (≈ 150 ms p50 on 4 CPU
cores, unloaded).
