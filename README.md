# Base Legal

**Every claim cites an inciso — and a machine checks it.**

Grounded, verifiable Q&A over Brazilian data protection law (LGPD, the Access
to Information Act and CD/ANPD resolutions). Answers cite the exact article, paragraph and inciso; each
citation is checked verbatim against the official text before it reaches
you, and when nothing in the corpus supports an answer, Base Legal says so.
Privacy by design, threat-modeled, eval-gated. MCP server included.

[![CI](https://github.com/lucianocf/base-legal/actions/workflows/ci.yml/badge.svg)](https://github.com/lucianocf/base-legal/actions/workflows/ci.yml)
[![Evals](https://github.com/lucianocf/base-legal/actions/workflows/evals.yml/badge.svg)](https://github.com/lucianocf/base-legal/actions/workflows/evals.yml)
[![recall@5](https://img.shields.io/endpoint?url=https://lucianocf.github.io/base-legal/badges/recall-at-5.json)](https://lucianocf.github.io/base-legal/evals/)
[![red-team](https://img.shields.io/endpoint?url=https://lucianocf.github.io/base-legal/badges/redteam.json)](https://lucianocf.github.io/base-legal/evals/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/lucianocf/base-legal/badge)](https://scorecard.dev/viewer/?uri=github.com/lucianocf/base-legal)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)

> **Not legal advice.** Base Legal is a research tool with no affiliation to
> the ANPD or the Brazilian government. See [LEGAL_NOTICE.md](LEGAL_NOTICE.md).
> 🇧🇷 [Leia em português](README.pt-BR.md).

<!-- TODO(author): replace with a GIF of question → answer → verified citations → refusal. -->
![Demo: a question, an answer with numbered citations to the official text, and a refusal](docs/assets/demo-placeholder.svg)

## Why this is different

- **Verified citations and strict refusal.** Claude answers from retrieved
  provisions with native Citations; every quote is re-checked verbatim
  against the provision it cites. Anything unsupported is replaced by
  "no support in the corpus" plus the nearest provisions (official text only).
- **It complies with the law it explains.** Questions are embedded **locally**
  (open-weight `voyage-4-nano`), so no embedding provider ever sees them;
  CPF, CNPJ, e-mail and phone numbers are redacted before the only third-party
  call; nothing is stored; logs carry no content. See [PRIVACY.md](docs/PRIVACY.md).
- **Threat-modeled and eval-gated.** STRIDE + OWASP LLM Top 10
  ([THREAT_MODEL.md](docs/THREAT_MODEL.md)); retrieval and red-team evals run
  on every pull request with no secrets; model weights and GitHub Actions
  pinned by hash.

## Quickstart

Requirements: Docker. An [Anthropic API key](https://console.anthropic.com/)
for generated answers (search, the web UI's search mode and the MCP server work
without one).

```bash
git clone https://github.com/lucianocf/base-legal.git && cd base-legal
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env            # git-ignored; optional
docker compose up -d --build                         # PostgreSQL + app, on 127.0.0.1
docker compose exec app base-legal ingest            # once; embeds the law on your CPU
docker compose exec app base-legal ask "Qual o prazo para comunicar um incidente de segurança à ANPD?"
```

Then open <http://127.0.0.1:8000> for the local web UI, or use the API
(`POST /ask`, `POST /search`, `GET /provisions/{id}`, `GET /provisions/{id}?at=AAAA-MM-DD`
for the wording in force on a past date, docs at `/docs`).

Without Docker: `uv sync --extra local`, `uv run base-legal model fetch`,
point `DATABASE_URL` at a PostgreSQL with pgvector, then the same
`base-legal ingest` / `ask` / `serve` commands via `uv run`.

### MCP (Claude Desktop, Claude Code)

A read-only MCP server exposes `search_provisions`, `get_provision` and
`verify_citation`; your MCP host's model writes the answer and Base Legal
never calls any third party:

```bash
claude mcp add base-legal \
  --env DATABASE_URL=postgresql://base_legal:base_legal@localhost:5432/base_legal \
  -- uv --directory /absolute/path/to/base-legal run base-legal mcp
```

Claude Desktop configuration: [docs/MCP.md](docs/MCP.md).

## How it works

```
question ─▶ PII redaction ─▶ local embedding (voyage-4-nano) ─┐
                           └▶ PostgreSQL full-text ────────────┼▶ RRF fusion ─▶ top-k provisions
                                                               │   (+ explicit "art. 7º, IX" lookups)
top-k ─▶ Claude (one cited document per provision) ─▶ citation validator ─▶ answer or refusal
```

- **Structural parsing** of the official texts into a provision tree with
  stable IDs: `lgpd:art7:incIX`, `lgpd:art65:incI-A`,
  `res-anpd-15-2024:anx1:art6` ([ADR 0002](docs/adr/0002-structural-chunking-canonical-ids.md),
  [ADR 0010](docs/adr/0010-annex-segment-in-provision-ids.md)).
- **Hybrid retrieval** in PostgreSQL: length-normalized full-text search and
  pgvector, fused with Reciprocal Rank Fusion, with a share of each hit's
  score propagated to its parent article ([ADR 0004](docs/adr/0004-postgres-hybrid-search-rrf.md)).
- **Grounded generation** with Claude Citations, one custom-content document
  per provision, so every citation maps to a canonical ID
  ([ADR 0005](docs/adr/0005-strict-grounding-verified-citations.md),
  [ADR 0011](docs/adr/0011-one-cited-document-per-provision.md)).
  Default model `claude-haiku-4-5`; `BASE_LEGAL_MODEL=claude-sonnet-5` for quality.

Details: [ARCHITECTURE.md](docs/ARCHITECTURE.md) and the [ADRs](docs/adr/).

## Evaluation

Golden set: 45 synthetic answerable questions and 8 that must be refused
(`evals/golden.yaml`, pending DPO review), split into dev (used for tuning)
and holdout (used only to confirm). Retrieval in `local` mode (voyage-4-nano
for documents and questions), as run in CI:

| Split | recall@5 | recall@10 | MRR | Refusal accuracy | False refusals |
|---|---|---|---|---|---|
| dev (31 + 5) | 67.7 % | 79.0 % | 0.474 | 60.0 % | 0.0 % |
| holdout (14 + 3) | 67.9 % | 82.1 % | 0.393 | 66.7 % | 0.0 % |

Before tuning, holdout recall@5 was 42.9 %. The red-team set (prompt
injection, PII, fake citations, XSS, oversized input) passes all 13
deterministic checks. The embedding validation gate compared five
configurations, and embedding the law with the same local model came first,
ahead of `voyage-4-large` documents
([results](docs/evals/embedding-gate.md), [ADR 0013](docs/adr/0013-voyage-4-nano-for-documents-by-default.md)).
Full reports: [docs/evals/](docs/evals/).

## Security and privacy

- [THREAT_MODEL.md](docs/THREAT_MODEL.md): data flows, trust boundaries,
  STRIDE and the OWASP Top 10 for LLM Applications (2025), each control
  linked to a test.
- [PRIVACY.md](docs/PRIVACY.md): the software's own data inventory (ROPA-style):
  what is processed, where it goes, for how long.
- [SECURITY.md](SECURITY.md): how to report a vulnerability.

## Corpus and legal notice

LGPD (Lei nº 13.709/2018, compiled text), LAI (Lei nº 12.527/2011, compiled
text) and Resoluções CD/ANPD nº 1/2021,
2/2022, 4/2023, 15/2024, 18/2024 and 19/2024 (Annex I), from planalto.gov.br,
gov.br/anpd and the Diário Oficial da União. Official acts are not protected
by copyright (Lei nº 9.610/1998, art. 8º, IV); provenance and hashes are in
`corpus/manifest.yaml`. See [LEGAL_NOTICE.md](LEGAL_NOTICE.md).

## Roadmap

- **Next: LAI × LGPD.** Lei nº 12.527/2011 (Access to Information Act) and the
  tension between transparency and data protection in the public sector.
- Resolved cross-references ("nos termos do art. 11" becomes a link).
- Res. CD/ANPD nº 19/2024 Annex II (standard contractual clauses).
- A static corpus explorer on GitHub Pages; a local reranker if evals show a gain.
- Point-in-time queries across the historical versions of the LGPD.

Full plan: [PLAN.md](docs/PLAN.md). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).

## Author

<!-- TODO(author): name, "DPO and information security, public sector", LinkedIn and Upwork links. -->

## License

Code: [Apache-2.0](LICENSE). Evaluation sets and documentation: CC BY 4.0.
Laws and resolutions: official acts, not protected by copyright.
