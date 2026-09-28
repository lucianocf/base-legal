# Retrieval eval: latest (dev)

Config: dense_weight=1.0, document_embedder=voyage-4-nano, fts_normalization=4, lexical_weight=0.5, mode=hybrid, parent_weight=0.2, query_embedder=voyage-4-nano, reranker=mmarco-mminilmv2 (depth 10), threshold=0.4

| Metric | Value |
|---|---|
| Answerable questions | 41 |
| Must-refuse questions | 5 |
| recall@1 | 42.7 % |
| recall@5 | 75.6 % |
| recall@10 | 79.3 % |
| hit@5 | 78.0 % |
| MRR | 0.591 |
| Refusal accuracy (must-refuse) | 100.0 % |
| False refusals (answerable) | 0.0 % |
| Latency p50 / p95 | 313 / 438 ms |

## Answerable questions without an expected provision in the top 5

| Item | Expected | Top 3 | Refused |
|---|---|---|---|
| g04 | lgpd:art5:incVI, lgpd:art5:incVII | lgpd:art50:par2:incI, lgpd:art50:par2, lgpd:art50 |  |
| g05 | lgpd:art5:incVIII, lgpd:art41:par2 | res-anpd-18-2024:anx1:art15:paru, res-anpd-18-2024:anx1:art15, res-anpd-18-2024:anx1:art15:paru:incI |  |
| g23 | lgpd:art38 | res-anpd-15-2024:anx1:art8, res-anpd-15-2024:anx1:art16:par1, res-anpd-1-2021:anx1:art35 |  |
| g24 | lgpd:art48:par1 | res-anpd-15-2024:anx1:art6:par2, res-anpd-15-2024:anx1:art6:par2:incXI, res-anpd-15-2024:anx1:art6:par2:incIV |  |
| g27 | lgpd:art52:incII | res-anpd-4-2023:anx1:art12, res-anpd-4-2023:anx1:art13, res-anpd-4-2023:anx1:art11 |  |
| g41 | lgpd:art65:incI-A | lgpd:art52:par1, lgpd:art52:par3, lgpd:art52 |  |
| g50 | lai:art10:par3 | lai:art8, lai:art11:par6, lai:art8:par1 |  |
| g51 | lai:art12 | lai:art12:par1, lai:art8, lai:art8:par1 |  |
| g54 | lai:art15 | lai:art16, lai:art16:incI, lai:art16:incII |  |
