# Contributing to Base Legal

Thanks for your interest. Base Legal is small on purpose: a typed Python
library with thin adapters (CLI, API, MCP server). Please read
[ARCHITECTURE.md](https://github.com/lucianocf/base-legal/blob/main/docs/ARCHITECTURE.md) and the [ADRs](https://github.com/lucianocf/base-legal/tree/main/docs/adr/) before
proposing structural changes.

Security issues: **do not open a public issue**; follow [SECURITY.md](https://github.com/lucianocf/base-legal/blob/main/SECURITY.md).

## Development setup

Requirements: [uv](https://docs.astral.sh/uv/) and PostgreSQL with pgvector
(`docker compose up -d db`).

```bash
uv sync --extra local              # Python 3.12, dev tools, local query model deps
uv run base-legal model fetch      # pinned voyage-4-nano, SHA-256 verified
uvx pre-commit install             # ruff, gitleaks, mypy on commit
```

Before pushing, run what CI runs:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src tests
DATABASE_URL=postgresql://base_legal:base_legal@localhost:5432/base_legal \
  uv run pytest --cov=base_legal --cov-fail-under=85
uv lock --check
```

Integration tests run in a throwaway schema, so they never touch your index.

Retrieval changes must be measured on the golden set:

```bash
uv run base-legal ingest --mode local
uv run base-legal eval retrieval --split dev       # tune here
uv run base-legal eval retrieval --split holdout   # confirm here, never tune
uv run base-legal eval redteam
```

## Conventions

- **Language:** code, comments, commits, ADRs and technical docs in English;
  corpus, golden-set questions, prompts and answers in Brazilian Portuguese.
  `README.pt-BR.md` mirrors `README.md`: update both in the same PR.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`, `refactor:`),
  imperative mood, small and focused.
- **Types and tests:** full type hints (`mypy --strict`), Pydantic at
  boundaries, no `Any` without a comment. Every bug fix comes with a
  regression test that fails without the fix. Parsing, grounding, privacy
  and retrieval fusion stay pure and unit-tested.
- **No RAG or agent frameworks** ([ADR 0001](https://github.com/lucianocf/base-legal/blob/main/docs/adr/0001-own-thin-code-no-rag-framework.md)).
- **Canonical provision IDs are a public API**: changing their format needs an ADR.
- **Decisions:** a significant decision gets a new ADR (copy
  `docs/adr/0000-template.md`); accepted ADRs are superseded, not edited.

## Privacy and security rules

- Never log question or answer text.
- PII redaction runs before any third-party call.
- User questions are never sent to an embedding API (ADR 0003).
- Model weights are pinned by revision and SHA-256; safetensors only.
- GitHub Actions are pinned by commit SHA with minimal `permissions:`.
- Test data is synthetic. Do not add real personal data, real cases, or any
  employer or client data to code, tests, docs or commits.

## Changing the corpus

1. `uv run base-legal corpus fetch --doc <id>` (updates the hash and date in
   `corpus/manifest.yaml`).
2. `uv run base-legal corpus build --doc <id>` and review the JSON diff
   against the official text.
3. Parser changes need a regression fixture built from a real excerpt.
4. Legal facts that are not confirmed in an official source are marked
   `TODO(verify)`.

`uv run base-legal corpus check` compares every official source with the
committed corpus provision by provision (raw-byte changes alone are ignored);
`--apply --report report.md` writes the changed acts and a review report. The
`Corpus watch` workflow runs it weekly and opens a draft pull request when the
law changed.

Earlier wordings (ADR 0014): `corpus build` writes `corpus/history/<doc>.json`
for compiled texts, and `uv run base-legal corpus acts` records in
`corpus/acts.yaml` when each amending act came into force, from its own page
(`--refresh` fetches them again). Run `corpus acts` before `corpus build`
when an amendment note names a new act, and review both diffs.

## Golden set

`evals/golden.yaml` holds synthetic questions only, each `unverified` until a
DPO reviews it. Keep the dev/holdout split stable: never move an item to dev
because it fails, and never tune on holdout.

## Releasing

Releases are cut by the maintainer only.

1. Set `version` in `pyproject.toml` (e.g. `0.1.0`), run `uv lock`, update the
   READMEs and merge.
2. Push a tag `vX.Y.Z` on that commit. The `Release` workflow checks that the
   tag matches the package version, builds the distributions and the image,
   and creates a **draft** GitHub release with the wheel, the sdist and a
   CycloneDX SBOM (`base-legal.cdx.json`).
3. Review the draft and publish it.

Verify what a release ships:

```bash
gh attestation verify base_legal-X.Y.Z-py3-none-any.whl --repo lucianocf/base-legal
gh attestation verify oci://ghcr.io/lucianocf/base-legal:X.Y.Z --repo lucianocf/base-legal
cosign verify ghcr.io/lucianocf/base-legal:X.Y.Z \
  --certificate-identity-regexp '^https://github.com/lucianocf/base-legal/\.github/workflows/release\.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

