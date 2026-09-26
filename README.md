# Base Legal

Citation-first RAG over Brazilian data protection law (LGPD + ANPD). Every
answer cites the exact article and inciso, and a machine checks each
citation against the corpus. Privacy by design, LLM threat model, MCP server.

> **Status: pre-alpha, under active development.** See the
> [project plan](docs/PLAN.md) and [architecture](docs/ARCHITECTURE.md).
> Nothing here is legal advice.

## What works today

- Structural parser for Brazilian legal acts → provision tree with stable
  canonical IDs (`lgpd:art7:incIX`, `lgpd:art48:par1:incIII`)
- Corpus provenance (URL, date, SHA-256) and integrity checks
- PII redaction (CPF/CNPJ with check digits, including the alphanumeric CNPJ;
  e-mail; phone) before any third-party call
- Citation validator with strict refusal
- Hybrid retrieval: explicit references, then PostgreSQL full-text + pgvector
  fused with RRF; questions embedded **locally** ([ADR 0003](docs/adr/0003-asymmetric-voyage-embeddings.md))
- CLI: `base-legal corpus fetch|build|embed`, `base-legal ingest`, `base-legal search`

Coming next: grounded answers with Claude, API, MCP server, evals in CI.

## Development

Requirements: [uv](https://docs.astral.sh/uv/) and a PostgreSQL with
pgvector (`docker compose up -d db`).

```bash
uv sync                                   # Python 3.12 + dev tools
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src tests
DATABASE_URL=postgresql://base_legal:base_legal@localhost:5432/base_legal \
  uv run pytest --cov=base_legal          # integration tests need DATABASE_URL
```

Local query embeddings need the optional extra: `uv sync --extra local`.
Maintainers embedding the law via the Voyage API need `--extra voyage` and
`VOYAGE_API_KEY` (public law text only; user questions never go to Voyage).

## Documentation

[Plan](docs/PLAN.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Threat model](docs/THREAT_MODEL.md) · [Privacy](docs/PRIVACY.md) ·
[ADRs](docs/adr/) · [Security policy](SECURITY.md)

## License

Code: [Apache-2.0](LICENSE). Laws and resolutions are official acts, not
protected by copyright (Lei nº 9.610/1998, art. 8º, IV).
