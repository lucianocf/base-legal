# 0001. Own thin code, no RAG framework

- Status: Proposed
- Date: 2026-09-26

## Context
RAG frameworks (LangChain, LlamaIndex, Haystack) offer loaders, splitters,
retrievers and eval helpers out of the box. This project is a portfolio
piece whose value lies in showing the engineering: how legal text is chunked,
how retrieval is fused, how citations are verified. It is also
security-focused, and every dependency adds supply chain surface (OWASP
LLM03). The pipeline is small: parse → chunk → embed → search → generate →
validate.

## Decision
Write the pipeline directly on top of the official SDKs (`anthropic`,
`voyageai`), `psycopg` 3, `pgvector`, Pydantic, FastAPI, the official MCP
Python SDK and Typer. No RAG or agent framework.

## Consequences
- ➕ Each step is visible, typed and unit-testable, so reviewers see the real design.
- ➕ A smaller dependency tree, easier to audit, faster CI.
- ➕ No framework abstractions to fight when implementing strict grounding.
- ➖ A few hundred more lines to write and maintain (loaders, RRF, eval runner).
- ➖ Framework integrations (tracing UIs, etc.) are not free. Acceptable at this scale.
