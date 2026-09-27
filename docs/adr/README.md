# Architecture Decision Records

Short records in the style of Michael Nygard: context, decision, consequences.
One decision per file, numbered sequentially and never renumbered. To change a
decision, add a new ADR that supersedes the old one and mark the old one as
`Superseded by NNNN`.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-own-thin-code-no-rag-framework.md) | Own thin code, no RAG framework | Proposed |
| [0002](0002-structural-chunking-canonical-ids.md) | Structural chunking and canonical provision IDs | Proposed |
| [0003](0003-asymmetric-voyage-embeddings.md) | Asymmetric Voyage 4 embeddings: API for the law, local model for questions | Proposed; documents superseded by 0013 |
| [0004](0004-postgres-hybrid-search-rrf.md) | PostgreSQL + pgvector + FTS hybrid search with RRF | Proposed |
| [0005](0005-strict-grounding-verified-citations.md) | Strict grounding: verified citations and refusal | Proposed |
| [0006](0006-no-hosted-llm-demo-pages-for-docs.md) | No hosted LLM demo in the MVP; GitHub Pages for docs and evals | Proposed |
| [0007](0007-licensing-code-data-corpus.md) | Licensing: code, data and corpus | Proposed |
| [0008](0008-default-generation-model.md) | Default generation model | Proposed |
| [0009](0009-no-redistribution-of-voyage-vectors-yet.md) | Do not redistribute voyage-4-large document vectors (yet) | Proposed |
| [0010](0010-annex-segment-in-provision-ids.md) | Annex segment in canonical provision IDs | Proposed |
| [0011](0011-one-cited-document-per-provision.md) | Generation: one cited document per provision | Proposed |
| [0012](0012-load-voyage-4-nano-without-remote-code.md) | Load voyage-4-nano without remote code, on transformers 5.x | Proposed |
| [0013](0013-voyage-4-nano-for-documents-by-default.md) | voyage-4-nano for documents by default (embedding gate result) | Proposed |

Template: [`0000-template.md`](0000-template.md).
