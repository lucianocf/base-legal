# Retrieval eval: latest (holdout)

Config: dense_weight=1.0, document_embedder=voyage-4-nano, fts_normalization=4, lexical_weight=0.5, mode=hybrid, parent_weight=0.2, query_embedder=voyage-4-nano, threshold=0.4

| Metric | Value |
|---|---|
| Answerable questions | 14 |
| Must-refuse questions | 3 |
| recall@1 | 17.9 % |
| recall@5 | 67.9 % |
| recall@10 | 82.1 % |
| hit@5 | 71.4 % |
| MRR | 0.393 |
| Refusal accuracy (must-refuse) | 66.7 % |
| False refusals (answerable) | 0.0 % |
| Latency p50 / p95 | 3245 / 3780 ms |

## Answerable questions without an expected provision in the top 5

| Item | Expected | Top 3 | Refused |
|---|---|---|---|
| g03 | lgpd:art5:incVI | lgpd:art50:par2:incI, lgpd:art41:par2, lgpd:art41 |  |
| g11 | lgpd:art11:incII:alig | lgpd:art11:incII, lgpd:art8, lgpd:art11:incII:alic |  |
| g26 | lgpd:art52 | res-anpd-4-2023:anx1:art16, res-anpd-4-2023:anx1:art24, res-anpd-4-2023:anx1:art3 |  |
| g28 | lgpd:art23:incIII | res-anpd-18-2024:anx1:art5, lgpd:art41:par2, lgpd:art41 |  |

## Must-refuse questions that were answered

| Item | Reason | Top 3 | Best similarity |
|---|---|---|---|
| r01 | out_of_corpus | lgpd:art52:par1, lgpd:art52, res-anpd-4-2023:anx1:art12 | 0.620 |
