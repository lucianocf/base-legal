# Overnight brief — road to v0.1.0

Autonomous work order for one long session. Work milestone by milestone
without asking for confirmation; the author is unavailable. Everything in
`CLAUDE.md` (especially the non-negotiable security and privacy rules) takes
precedence over this brief.

## 0. Setup
1. Read, in order: `CLAUDE.md`, `docs/PLAN.md`, `docs/ARCHITECTURE.md`,
   `docs/adr/*`, `docs/THREAT_MODEL.md`, `docs/PRIVACY.md`,
   `docs/golden-set-draft.md`.
2. Check and record in the report:
   - Network: www.planalto.gov.br (needs the `Mozilla/5.0 (compatible; ...)`
     user agent, already configured in the fetcher), www.in.gov.br,
     www.gov.br, huggingface.co, api.voyageai.com.
   - `VOYAGE_API_KEY` present (env var or environment API credential); test
     with one embedding call on public law text.
   - PostgreSQL + pgvector: without Docker, run `pgserver` from a venv in
     `.pgserver/` (git-ignored). Postgres runs as another user, so the data
     dir must be readable by it (use the project folder, not /tmp).
   - `uv sync --extra local --extra voyage`, then `uv run base-legal model fetch`.
   - Full suite green: ruff, `mypy --strict`, pytest with `DATABASE_URL`.

## Milestones (in order; commit and push at the end of each)
Each ends with green checks, small Conventional Commits (English), a push,
and a line in the report. If one is blocked by something external, record
it, do what is possible without it, and move on.

**M1 — Law vectors with voyage-4-large.** `base-legal corpus embed` over the
public LGPD text (`corpus/lgpd.json`). Check Voyage's terms on
redistributing generated embeddings. Allowed → commit `corpus/embeddings/`
and update the manifest. Not allowed or unclear → don't commit; document and
keep `api`/`local` modes. Clear the matching `TODO(verify)` in ADR 0003 and PLAN.

**M2 — CD/ANPD resolutions.** Find the official URLs (DOU/in.gov.br or
gov.br/anpd) for Resolutions 1/2021, 2/2022, 4/2023, 15/2024, 18/2024 and
19/2024. Confirm numbers and ementas (the first three were from memory) and
look for amending resolutions. Add them to the manifest, fetch and build,
and adapt the parser to the DOU layout, with regression tests built from real
excerpts. Res. 19 annexes are a documented follow-up. Review the output
against the official text, as was done for the LGPD.

**M3 — Golden set and retrieval evaluation.** Turn
`docs/golden-set-draft.md` into `evals/golden.yaml` and `evals/redteam.yaml`
marked `status: unverified` (the author will validate). Fix IDs that do not
exist in the real corpus; resolve the ⚠ resolution rows. Implement
`base-legal eval retrieval`: recall@1/5/10, MRR, refusal accuracy
(nonexistent references, out-of-scope questions), p50/p95 latency. Output
JSON and Markdown. Split into dev and holdout sets to avoid overfitting.

**M4 — Embedding validation gate (ADR 0003) and retrieval tuning.** Run
B0 (FTS only), B1 (voyage-4-large docs + nano queries), B2 (nano + nano),
B3 (Qwen3-Embedding-0.6B), B4 (BGE-M3), each dense-only and hybrid. Qwen and
BGE are benchmark-only: pin revision + SHA-256, never production
dependencies. Publish `docs/evals/embedding-gate.md` and apply the ADR 0003
rule (keep B1 unless B3 beats it on hybrid recall@5 by more than 3 points);
a changed decision needs a new ADR.

Then tune retrieval using the dev set only, confirmed on the holdout. Known
failures with nano + nano: "vazamento… avisar a ANPD" should return
`lgpd:art48`; "levar meus dados para outra empresa" should return
`lgpd:art18:incV`. Hypotheses: OR full-text favors long chunks (art. 60
matches everything), missing parent/child expansion, uncalibrated refusal
threshold. Record before and after.

**M5 — Grounded generation.** Load the `claude-api` skill before writing
any LLM code. Implement `base_legal.generation` per ADR 0005 and
ARCHITECTURE:
- native Citations with a custom-content document, one block per provision;
- map each cited block to its canonical ID;
- validate with `grounding.judge`, strict refusal plus the nearest provisions;
- prompt caching on the system prompt; capped `max_tokens`.

The model comes from config (`BASE_LEGAL_MODEL`, default `claude-haiku-4-5`,
alternative `claude-sonnet-5`). First confirm that Haiku 4.5 supports
Citations; if not, use the structured-output fallback from ADR 0005.
Add `base-legal ask`. PII redaction runs first. Tests use a fake client; if
Anthropic credentials are available, run one short live test and record its
cost. No LLM calls in CI.

**M6 — API and minimal UI.** FastAPI with:
- `POST /ask`, `POST /search`, `GET /provisions/{id}`, `GET /health`;
- size and k limits, a simple rate limit;
- security headers, strict CSP, localhost bind by default;
- the "not legal advice" disclaimer in every response;
- no question text in logs, proven by a log-capture test.

One static HTML page served by the API, no third-party scripts, rendering
responses as text (never innerHTML).

**M7 — Read-only MCP server.** Official MCP Python SDK, stdio transport.
Tools: `search_provisions`, `get_provision`, `verify_citation`. It never
calls Claude and has no tools with side effects; a test asserts this.
End-to-end test with an in-process MCP client. Document the Claude Desktop
and Claude Code configuration.

**M8 — Evals in CI and badge.** A workflow for retrieval evals,
deterministic and secret-free: nano weights cached by lockfile hash; law
vectors from the repo, or `local` mode if they cannot be redistributed.
Include the deterministic red-team checks (redaction, validator, refusal).
Emit a badge JSON. Actions pinned by SHA, minimal permissions.

**M9 — Docker image and full compose.** Multi-stage build, non-root user,
model baked into the image with hash verification at build time, offline
runtime for models. `compose.yaml` runs DB + app. The README quickstart must
work from a fresh clone. Validate what is possible without Docker; record
what could not be validated.

**M10 — Publish-ready docs.**
- Full `README.md` (EN) and `README.pt-BR.md` following
  `docs/VISIBILITY.md` (the GIF may be a placeholder);
- `LEGAL_NOTICE.md`, `CONTRIBUTING.md`;
- MkDocs Material + GitHub Pages workflow, including the eval report;
- update PLAN (publish checklist), ARCHITECTURE, THREAT_MODEL, PRIVACY and
  CLAUDE.md to match what was built.

Every legal statement is either checked against the official text or marked
`TODO(verify)`.

**M11 — PR and green CI.** Open a draft PR from the branch to `main`
(follow the repo's PR template if one exists). Drive CI to green by fixing
the root cause of each failure. No merge, no release tag, no package publish.

**Stretch, only if everything above is done:**
- LAI corpus (Lei nº 12.527/2011) with the same pipeline;
- resolved cross-references ("nos termos do art. 11" becomes a link);
- a static corpus explorer on GitHub Pages.

## Known issues (fix when relevant)
- Integration tests share the DB and leave `index_meta` set to
  `test-hashing`. Isolate them with a dedicated database or schema per test
  session.
- `Manifest.dump` drops YAML comments. Move the TODOs to PLAN or preserve
  the comments.
- `html.py` keeps only innermost blocks and may lose text from a `<p>` that
  contains other blocks. Check against the real corpus.
- Art. 55-B (fully struck) is absent from the corpus. Decide whether the
  revocation history should be recorded.

## Working rules
- Decide alone when a reasonable choice exists. Record significant
  decisions in a new ADR (`docs/adr/0000-template.md`); never edit accepted ADRs.
- Before each push: ruff, `mypy --strict`, pytest with coverage ≥ 85 %,
  `uv lock --check`. Every bug fix gets a regression test that fails without
  the fix.
- No metric overfitting: every retrieval change is confirmed on the holdout.
- Never invent legal facts, norm numbers or vendor policies. Confirm them in
  the primary source or mark them `TODO(verify)`.
- Never push to `main`, force-push, merge or release.
- Costs: embeddings of public law text only; Claude calls only in short live
  tests, never in CI.

## Report
Keep `docs/progress/2026-09-27-overnight.md` up to date, committed at the end
of each milestone:
- environment status;
- milestones done, partial and blocked, with the reason;
- metrics before and after;
- decisions taken, with ADR links;
- open `TODO(verify)` items;
- what needs the author: golden-set validation, GitHub settings (private
  vulnerability reporting, Pages, public repo), legal text review.
