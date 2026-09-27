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
| M2 CD/ANPD resolutions | pending | |
| M3 Golden set + retrieval eval | pending | |
| M4 Embedding gate + tuning | pending | |
| M5 Grounded generation | pending | |
| M6 API + UI | pending | |
| M7 MCP server | pending | |
| M8 Evals in CI + badge | pending | |
| M9 Docker image + compose | pending | |
| M10 Publish-ready docs | pending | |
| M11 Draft PR + green CI | pending | |

## Metrics (before → after)

_Filled in from M3 onwards._

## Decisions

- [ADR 0009](../adr/0009-no-redistribution-of-voyage-vectors-yet.md): do not
  redistribute `voyage-4-large` vectors until Voyage confirms in writing.
  CI and published evals use `local` mode.

## Open `TODO(verify)` items

_Consolidated at the end._

## What needs the author

_Consolidated at the end._
