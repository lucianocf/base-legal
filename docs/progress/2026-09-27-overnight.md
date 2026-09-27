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
| M9 Docker image + compose | 🟡 in progress | Multi-stage non-root image (uid 10001), base images by digest, nano fetched and SHA-256-verified at build time, offline runtime, read-only rootfs + `cap_drop: ALL` in compose, app and DB on 127.0.0.1. Running the stack found two real bugs (fixed, regression tests): `serve` crashed on a fresh DB; empty `VOYAGE_API_KEY` from compose made `ingest` pick the API. Image 3.3 GB (CPU torch + weights). Final end-to-end rerun pending after the transformers 5 upgrade. |
| M10 Publish-ready docs | ✅ done (gate page pending) | README EN/PT-BR, LEGAL_NOTICE (art. 8º, IV of Lei 9.610/1998 verified at planalto.gov.br), CONTRIBUTING, MkDocs Material + Pages workflow with eval report and badges, THREAT_MODEL (control → test map), PRIVACY, ARCHITECTURE (settings table), PLAN §9 checklist, CLAUDE.md. |
| M11 Draft PR + green CI | 🟡 in progress | Draft PR [lucianocf/base-legal#1](https://github.com/lucianocf/base-legal/pull/1). First CI run found: pip-audit could not audit `torch+cpu` and then **real transformers 4.x CVEs** → nano now loads without remote code on transformers 5.17 ([ADR 0012](../adr/0012-load-voyage-4-nano-without-remote-code.md), identical embeddings); gitleaks false positive on lock digests; **3 CodeQL high alerts** (case-sensitive `<script>` checks, polynomial e-mail regex) fixed and re-verified with a local CodeQL 2.27.1 run (0 results); mypy without extras. |

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
- [ADR 0010](../adr/0010-annex-segment-in-provision-ids.md): annex segment in
  canonical IDs (`res-anpd-15-2024:anx1:art6`); additive, no existing ID changes.
- [ADR 0011](../adr/0011-one-cited-document-per-provision.md): one cited
  custom-content document per provision (Citations on Haiku 4.5 confirmed).
- [ADR 0012](../adr/0012-load-voyage-4-nano-without-remote-code.md): nano
  without remote code, on transformers 5.x (closes the transformers 4.x CVEs).
- Retrieval defaults tuned on dev and confirmed on holdout
  ([retrieval-tuning.md](../evals/retrieval-tuning.md)); a tighter refusal
  threshold was rejected for overfitting.

## Open `TODO(verify)` items

| Where | What | Needs |
|---|---|---|
| `docs/PRIVACY.md` §1, §4 | Anthropic's current data retention and training terms | Read at each release (legal review) |
| `docs/adr/0008` | Cost per question with measured token counts | One live `ask` run with an Anthropic key |
| `docs/adr/0011` | Whether prompt caching ever triggers (Haiku 4.5 minimum prefix is 4,096 tokens) | Live run: `usage.cache_read_input_tokens` |
| `docs/MCP.md` | MCP configuration inside Claude Desktop and Claude Code | Run in both hosts |
| `docs/adr/0007` | Licence stated on the ANPD portal for guides (Phase 3 only) | Before adding ANPD guides |
| `README*.md` | Demo GIF and author section (`TODO(author)`) | The author |

Closed tonight: Voyage redistribution (ADR 0009), resolution numbers, dates
and amendments (PLAN §7), Citations on Haiku 4.5 (ADR 0005/0011),
Lei 9.610/1998 art. 8º, IV (LEGAL_NOTICE).

## What needs the author

1. **Golden and red-team sets:** validate every item (`status: unverified`);
   in particular the ⚠ rows now resolved to annex articles (g25, g31–g34,
   g40) and g15/g16 narrowed to alíneas. Re-run the tuning grid on dev after
   validation.
2. **Live generation:** set `ANTHROPIC_API_KEY` and run
   `base-legal ask` on a few golden questions; record cost, refusal rate and
   whether caching triggers (ADR 0008, 0011).
3. **GitHub settings:** enable Pages with "GitHub Actions" as the source
   (badges and the eval report live there), private vulnerability reporting
   (SECURITY.md), make the repository public, set description and topics
   (VISIBILITY §2). Code scanning is already active.
4. **MCP:** try `base-legal mcp` in Claude Desktop and Claude Code (`docs/MCP.md`).
5. **Employer separation:** run the prohibited-terms grep with your own term
   list and review; commit identities are the GitHub noreply address and the
   Claude session identity.
6. **Voyage:** optionally ask `legal@voyageai.com` in writing whether
   embeddings of public-domain text may be redistributed (ADR 0009); a yes
   enables the zero-key B1 quickstart.
7. **README:** demo GIF and author section; release notes and the `v0.1.0`
   tag after merging (not done by design: no merge, no release).
8. **Legal text review:** spot-check the parsed resolutions against the DOU
   (the automated verbatim check passed; three quoted-amendment differences
   are elision spacing only).
