# 0011. Generation: one cited document per provision

- Status: Proposed
- Date: 2026-09-27

## Context
ADR 0005 chose Claude's native Citations with **one custom-content document
in which each content block is one provision**, mapping
`content_block_location` block indices to canonical IDs.

Facts checked on 2026-09-27 in the Citations documentation
(<https://platform.claude.com/docs/en/build-with-claude/citations>):

- "All active models support citations", so `claude-haiku-4-5` (the
  default, ADR 0008) and `claude-sonnet-5` both do. The structured-output
  fallback of ADR 0005 is not needed.
- For custom content, "your provided content blocks are used as-is"; a
  citation returns the block range (`start_block_index`, exclusive
  `end_block_index`) and `cited_text` is the content of those blocks.
- A document's `title` and `context` "are passed to the model but not used
  toward cited content".
- Citations and `output_config.format` cannot be combined (400).

Putting several provisions in one document raises two problems. The model
needs to know which provision each block is (its label and hierarchy), but
any label written *inside* the block becomes part of `cited_text`, and the
validator (ADR 0005 §2) would then reject every quote as not verbatim. A
bare inciso ("quando necessário para atender aos interesses legítimos…")
also means little without its caput.

## Decision
- Each retrieved provision is sent as **its own custom-content document**
  with exactly one content block: the official provision text.
- `title` carries the canonical ID and the hierarchy path;
  `context` carries the path and the ancestors' text (e.g. the caput above an
  inciso), clipped to 600 characters. Neither is citable.
- `document_index` maps to the canonical ID deterministically (document `i`
  is retrieved provision `i`). An unmappable citation is turned into an
  unknown ID, so the validator rejects it.
- Everything else in ADR 0005 stands: the validator re-checks every citation,
  strict refusal replaces any ungrounded answer with the nearest provisions
  (official text only), and a model answer of exactly `SEM_BASE` is a
  refusal too. `stop_reason` `refusal` and `max_tokens` also refuse.
- The system prompt (PT-BR, static, in the repo) carries all instructions and
  a `cache_control` marker. It is far below Haiku 4.5's 4,096-token minimum
  cacheable prefix (1,024 on Sonnet 5), so on the default model the marker
  has no effect today; padding the prompt to reach the minimum is not worth
  it at this size.

## Consequences
- ➕ Quotes are the provision text itself, so valid citations pass the
  verbatim check by construction and the citation-validity metric is 100 %.
- ➕ The model sees the hierarchy and the caput without being able to cite
  them as if they were the provision.
- ➖ More document blocks per request (one per provision, default k = 8),
  with slightly more framing tokens than a single document.
- ➖ Citation granularity is the whole provision: a long paragraph is cited
  as a whole. Acceptable, since provisions are the unit of citation anyway.
- ➖ Prompt caching saves nothing on Haiku 4.5 until the static prefix grows
  past 4,096 tokens (`TODO(verify)` with measured usage in a live run).
