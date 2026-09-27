# Retrieval eval: latest (holdout)

Config: dense_weight=1.0, document_embedder=voyage-4-nano, fts_normalization=4, lexical_weight=0.5, mode=hybrid, parent_weight=0.2, query_embedder=voyage-4-nano, reranker=mmarco-mminilmv2 (depth 10), threshold=0.4

| Metric | Value |
|---|---|
| Answerable questions | 18 |
| Must-refuse questions | 4 |
| recall@1 | 30.6 % |
| recall@5 | 66.7 % |
| recall@10 | 69.4 % |
| hit@5 | 66.7 % |
| MRR | 0.500 |
| Refusal accuracy (must-refuse) | 100.0 % |
| False refusals (answerable) | 0.0 % |
| Latency p50 / p95 | 316 / 391 ms |

## Answerable questions without an expected provision in the top 5

| Item | Expected | Top 3 | Refused |
|---|---|---|---|
| g11 | lgpd:art11:incII:alig | lgpd:art8, lgpd:art11:incII:alic, lgpd:art5:incXII |  |
| g14 | lgpd:art6:incIII | lai:art31:par3, lai:art8:par3, lai:art31:par3:incI |  |
| g26 | lgpd:art52 | res-anpd-4-2023:anx1:art24, res-anpd-4-2023:anx1:art16, res-anpd-4-2023:anx1:art24:par3 |  |
| g28 | lgpd:art23:incIII | res-anpd-18-2024:anx1:art5, res-anpd-18-2024:anx1:art5:par3, lgpd:art41:par2 |  |
| g34 | res-anpd-18-2024:anx1:art18, res-anpd-18-2024:anx1:art19:par1 | res-anpd-18-2024:anx1:art21:paru, res-anpd-18-2024:anx1:art21:paru:incI, res-anpd-18-2024:anx1:art21:paru:incIII |  |
| g45 | lgpd:art52 | res-anpd-4-2023:anx1:art17:par3:incII, res-anpd-4-2023:anx1:art13:incIII, res-anpd-4-2023:anx1:art12 |  |
