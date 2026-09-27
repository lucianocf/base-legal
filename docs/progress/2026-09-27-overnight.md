# Overnight report — road to v0.1.0 (2026-09-27)

Work order: [`overnight-brief.md`](overnight-brief.md). Branch:
`claude/bold-gauss-18wxg2`. This file is updated at the end of every milestone.

## Environment status

| Check | Result |
|---|---|
| www.planalto.gov.br (project UA) | ✅ 200 |
| www.in.gov.br | ✅ reachable (301 → portal) |
| www.gov.br/anpd | ✅ 200 |
| huggingface.co | ✅ 200 |
| api.voyageai.com | ✅ reachable; key present, one `voyage-4-large` call on public law text OK (18 tokens) |
| Anthropic API key | ❌ not present in the environment: no live Claude test possible |
| PostgreSQL + pgvector | ✅ `pgserver` (PostgreSQL 16, pgvector 0.6.2) in `.pgserver/`, Unix socket |
| Docker | ✅ client present; daemon started manually (`dockerd`) |
| `uv sync --extra local --extra voyage` | ✅ |
| `base-legal model fetch` | ✅ 13 files, all SHA-256 verified (672 MB) |
| Baseline suite | ✅ ruff, mypy `--strict`, 118 tests, 91 % coverage, `uv lock --check` |

Observations:
- Planalto returns different bytes between fetches for identical content
  (the LGPD page hash changed overnight; the parsed provisions are identical).
  `corpus fetch` will therefore report spurious "changed". Follow-up: compare
  the parsed output, not only the raw hash, before re-snapshotting.

Parser bugs found while reviewing the real resolutions (all with regression tests):
- gov.br strikes some revoked paragraphs *with their label* (Res. 1/2021
  annex art. 35 § 4º and art. 36 § 3º, revoked by Res. 4/2023 art. 3). The
  surviving "(Revogado …)" note was attached to the in-force paragraph above.
  The same happened in the LGPD (art. 55 and the struck art. 55-B, whose note
  landed on art. 55-A). Orphan notes are now dropped.
- Unnumbered rubrics before articles ("Intimação", "Recurso ao Conselho
  Diretor da ANPD") were glued to the previous provision's text (17 cases in
  Res. 1/2021). They now join the path of the following articles.
- Known issue "html.py keeps only innermost blocks": fixed by breaking lines
  at every block boundary (gov.br headings live in bare `<div>`s).
- Known issue "Manifest.dump drops YAML comments": fixed (leading comment
  block kept; regression test).
- Known issue "Art. 55-B absent": decided. Provisions struck together with
  their label cannot be identified reliably (Planalto also strikes superseded
  wording of provisions still in force), so revocation history is not
  recorded; point-in-time support (Phase 3) will use historical versions.

Setup fixes:
- `mypy --strict` failed only when the `voyage` extra was installed
  (`voyageai` does not re-export `Client`); fixed with a mypy override so the
  check is identical with or without extras.
- Known issue "integration tests share the DB": fixed. Each test session now
  runs in a throwaway schema (`test_<random>`) dropped at the end, so a
  developer's index is never touched. Regression test included.

## Milestones

| Milestone | Status | Notes |
|---|---|---|
| M1 Law vectors (voyage-4-large) | ✅ done (vectors **not** committed) | 435 LGPD vectors generated. Voyage ToS (2026-05-27) is silent on outputs → not redistributed ([ADR 0009](../adr/0009-no-redistribution-of-voyage-vectors-yet.md)); vectors stay local with a git-ignored sidecar. Free tier (3 RPM / 10K TPM) forced token-budgeted batching + backoff. |
| M2 CD/ANPD resolutions | ✅ done | 6 resolutions (846 provisions) confirmed against the ANPD index of regulations; numbers, dates, ementas and amendments verified (Res. 1/2021 ← Res. 4/2023; Res. 2/2022 ← Res. 15/2024; Res. 19/2024 ← DOU correction of 18/08/2025, Annex II only). New `dou` and `govbr` layouts, annex IDs ([ADR 0010](../adr/0010-annex-segment-in-provision-ids.md)). Output reviewed: every provision text is verbatim in its official page (3 exceptions, all "(...)" spacing in quoted amendments, checked by hand); article numbering has no gaps. Res. 19/2024 Annex II (standard clauses) is a follow-up. |
| M3 Golden set + retrieval eval | ✅ done | `evals/golden.yaml` (45 answerable + 8 must-refuse, all `unverified`) and `evals/redteam.yaml` (10 cases with deterministic checks). All draft IDs exist; ⚠ rows resolved to the regulations' annex articles; g15/g16 narrowed to the exact alíneas. Stratified dev/holdout (31+5 / 14+3). `base-legal eval retrieval` → JSON + Markdown. |
| M4 Embedding gate + tuning | pending | |
| M5 Grounded generation | ✅ done (live test blocked) | `base_legal.generation` + `base-legal ask`. Citations on `claude-haiku-4-5` confirmed in the docs ("all active models support citations"); one custom-content document per provision ([ADR 0011](../adr/0011-one-cited-document-per-provision.md)). PII redaction first; retrieval refusals never call the model; validator + strict refusal. **Live test not run: no Anthropic credential in the environment** (cost not measured). |
| M6 API + UI | ✅ done | FastAPI `/ask`, `/search`, `/provisions/{id}`, `/health`; length/k limits, rate limit, optional API key, strict CSP + security headers, disclaimer in every body, 422s never echo input, content-free request log (log-capture tests). Static UI renders with `textContent`. Smoke-tested live with `base-legal serve`. |
| M7 MCP server | ✅ done | Official MCP SDK **2.x** (`MCPServer`); 3 read-only tools; stdio end-to-end test in a subprocess where constructing an Anthropic client aborts. Host config in `docs/MCP.md` (not yet tried inside Claude Desktop/Code). |
| M8 Evals in CI + badge | ✅ done (CI run pending the PR) | `.github/workflows/evals.yml`: secret-free, nano cached by lockfile hash and re-verified, `local` ingest, gates recall@5 ≥ 0.65 / refusal ≥ 0.6 / red-team 100 %; `base-legal eval redteam` (13 deterministic checks, all passing locally); shields.io badge JSON. actionlint + zizmor clean. |
| M9 Docker image + compose | pending | |
| M10 Publish-ready docs | pending | |
| M11 Draft PR + green CI | pending | |

## Metrics (before → after)

Baseline ("before"): full corpus (7 acts, 1,281 chunks), `local` mode
(voyage-4-nano for documents and questions), hybrid RRF, no refusal
threshold. Golden set of 2026-09-27.

| Split | recall@1 | recall@5 | recall@10 | MRR | Refusal acc. | False refusals | p50 / p95 |
|---|---|---|---|---|---|---|---|
| dev (31 + 5) | 19.4 % | 33.9 % | 50.0 % | 0.292 | 40.0 % | 0.0 % | 148 / 177 ms |
| holdout (14 + 3) | 21.4 % | 42.9 % | 67.9 % | 0.326 | 33.3 % | 0.0 % | 146 / 198 ms |

After tuning on dev (M4; confirmed on holdout):

| Split | recall@1 | recall@5 | recall@10 | MRR | Refusal acc. | False refusals |
|---|---|---|---|---|---|---|
| dev (31 + 5) | 27.4 % | 67.7 % | 79.0 % | 0.474 | 60.0 % | 0.0 % |
| holdout (14 + 3) | 17.9 % | 67.9 % | 82.1 % | 0.393 | 66.7 % | 0.0 % |

Knobs (all chosen on dev): `ts_rank_cd` normalization 4 (the long-chunk bias
was the biggest single problem: normalization alone took dev recall@5 from
33.9 % to 62.9 %), lexical weight 0.5 in RRF, 0.2 of each hit's score
propagated to its ancestors, refusal threshold 0.40. A tighter threshold
(0.47, the dev optimum) was **rejected** on holdout (14 % false refusals).
Holdout recall@1 fell slightly (21.4 % → 17.9 %). g43 (vazamento) is fixed
(rank 2); g44 (portabilidade) improved to rank 8 but is still outside the top 5.

Main baseline failure pattern: children crowd out the parent the question is about
(art. 7 → art. 7 § 7; art. 18 → §§ 1–3; Res. 15 art. 6 → § 1), and the two
known failures (g43 "vazamento… avisar a ANPD", g44 "levar meus dados para
outra empresa") miss.

## Decisions

- [ADR 0009](../adr/0009-no-redistribution-of-voyage-vectors-yet.md): do not
  redistribute `voyage-4-large` vectors until Voyage confirms in writing.
  CI and published evals use `local` mode.

## Open `TODO(verify)` items

_Consolidated at the end._

## What needs the author

_Consolidated at the end._
