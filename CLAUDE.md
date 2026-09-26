# CLAUDE.md — Project conventions for Base Legal

Base Legal is a citation-first RAG over Brazilian data protection law (LGPD +
CD/ANPD resolutions). Read `docs/PLAN.md` and `docs/ARCHITECTURE.md` before
changing anything structural. Decisions live in `docs/adr/`.

## Current phase
Weekend 1 core is implemented (parser, IDs, PII redaction, grounding
validator, hybrid retrieval, CLI, CI). Pending: the real corpus (LGPD from
Planalto, CD/ANPD resolutions from the DOU), pinning `voyage-4-nano`, and the
embedding validation gate (ADR 0003). The parser has only been tested on a
synthetic fixture: validate it against the official text before relying on it.
For local integration tests without Docker, `.pgserver/` (git-ignored) can run
PostgreSQL + pgvector via the `pgserver` package.

## Language
- Code, identifiers, comments, commits, ADRs and technical docs: **English**.
- `README.pt-BR.md` mirrors `README.md`; update both in the same PR.
- Corpus, golden-set questions, prompts to the model and answers: **PT-BR**.

## Stack and commands
- Python 3.12, `uv` for dependencies (commit `uv.lock`).
- Lint/format: `uv run ruff check . && uv run ruff format --check .`
- Types: `uv run mypy --strict src tests`
- Tests: `uv run pytest --cov=base_legal` (≥ 85 % on core packages)
- Local stack: `docker compose up -d` (PostgreSQL + pgvector)
- Evals: `uv run base-legal eval` (retrieval evals are deterministic and use
  the local query embedder; don't add paid API calls or secrets to CI).
- Run all of the above before pushing; pre-commit enforces lint and gitleaks.

## Code conventions
- Library-first: all logic in `src/base_legal/<package>`; CLI, API, MCP and UI
  are thin adapters. No RAG/agent frameworks (ADR 0001).
- Full type hints, Pydantic models at boundaries, no `Any` without a comment.
- `grounding`, `privacy`, `corpus` parsing and `retrieval` fusion must be pure
  and unit-tested. Every bug fix comes with a regression test.
- Canonical provision IDs (`lgpd:art7:incIX`) are a public API: never change
  the format without a new ADR.
- Model IDs come from configuration (`BASE_LEGAL_MODEL`), never hardcoded in
  logic. Defaults: `claude-haiku-4-5`, alternative `claude-sonnet-5`.

## Security and privacy rules (non-negotiable)
- **Never log question or answer text** unless `BASE_LEGAL_LOG_QUESTIONS=true`,
  and even then only redacted text.
- Run PII redaction **before** any call to Anthropic.
- **Never send user questions to Voyage.** Questions are embedded locally with
  `voyage-4-nano`; the Voyage API is only for embedding public law text
  (ADR 0003). Any hosted reranker or embedder for queries needs a new ADR.
- Model weights: pin by revision + SHA-256, safetensors only, no
  `trust_remote_code` unless reviewed and pinned.
- Treat all text as untrusted: questions, corpus and model output. No model
  tools with side effects; the MCP server stays read-only.
- Render model/corpus text as text in the UI (no `innerHTML`); keep the strict CSP.
- Secrets only via environment variables; never commit `.env`.
- Pin GitHub Actions by SHA; workflows declare minimal `permissions:`.
- Changes to `corpus/` must update `manifest.yaml` (URL, date, SHA-256) and be
  reviewed as a diff.
- **No employer data, names or internal references anywhere**: code, docs,
  examples, commits or test fixtures. Test PII is synthetic.
- The golden set contains synthetic questions only.

## Commits and PRs
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`,
  `refactor:`), imperative mood, small and focused.
- Don't put model identifiers in commit messages, PR titles or code comments.
- Update `docs/THREAT_MODEL.md` / `docs/PRIVACY.md` when a PR adds a data flow,
  interface or third party.

## ADRs
- New decision → copy `docs/adr/0000-template.md` to the next number, add it to
  `docs/adr/README.md`. Don't edit accepted ADRs; supersede them.

## Unverified facts
Mark anything not confirmed from a primary source as `TODO(verify)` rather than
stating it. Legal content in particular must be checked against official texts.
