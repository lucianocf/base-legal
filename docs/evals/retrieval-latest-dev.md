# Retrieval eval: latest (dev)

Config: dense_weight=1.0, document_embedder=voyage-4-nano, fts_normalization=4, lexical_weight=0.5, mode=hybrid, parent_weight=0.2, query_embedder=voyage-4-nano, threshold=0.4

| Metric | Value |
|---|---|
| Answerable questions | 31 |
| Must-refuse questions | 5 |
| recall@1 | 27.4 % |
| recall@5 | 67.7 % |
| recall@10 | 79.0 % |
| hit@5 | 74.2 % |
| MRR | 0.474 |
| Refusal accuracy (must-refuse) | 60.0 % |
| False refusals (answerable) | 0.0 % |
| Latency p50 / p95 | 3168 / 3720 ms |

## Answerable questions without an expected provision in the top 5

| Item | Expected | Top 3 | Refused |
|---|---|---|---|
| g04 | lgpd:art5:incVI, lgpd:art5:incVII | lgpd:art41:par2, lgpd:art50:par2:incI, lgpd:art41 |  |
| g23 | lgpd:art38 | res-anpd-15-2024:anx1:art8, res-anpd-1-2021:anx1:art20:par1, res-anpd-1-2021:anx1:art35 |  |
| g24 | lgpd:art48:par1 | res-anpd-15-2024:anx1:art6:par2, res-anpd-15-2024:anx1:art9, res-anpd-15-2024:anx1:art5 |  |
| g27 | lgpd:art52:incII | res-anpd-4-2023:anx1:art11, res-anpd-4-2023:anx1:art12, res-anpd-4-2023:anx1:art13 |  |
| g31 | res-anpd-19-2024:anx1:art15 | res-anpd-19-2024:anx1:art18, res-anpd-19-2024:anx1:art16, res-anpd-19-2024:anx1:art18:par1 |  |
| g35 | lgpd:art42:par1:incI | lgpd:art48, lgpd:art43, lgpd:art44 |  |
| g41 | lgpd:art65:incI-A | lgpd:art52, lgpd:art52:par1, res-anpd-1-2021:anx1:art37 |  |
| g44 | lgpd:art18:incV | lgpd:art33, res-anpd-19-2024:anx1:art9, res-anpd-19-2024:anx1:art9:incII |  |

## Must-refuse questions that were answered

| Item | Reason | Top 3 | Best similarity |
|---|---|---|---|
| r05 | out_of_corpus | res-anpd-4-2023:anx1:art3, res-anpd-4-2023:anx1:art8, res-anpd-4-2023:anx1:art8:par3:incI | 0.423 |
| r08 | out_of_corpus | lgpd:art18, lgpd:art9, lgpd:art2:incVI | 0.464 |
