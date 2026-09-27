# 0008. Default generation model

- Status: Proposed
- Date: 2026-09-26

## Context
The generation step is constrained: answer from supplied provisions, cite
them, refuse otherwise. The budget is close to zero, and evals of
generation run locally or on demand.

## Decision
- Default model: **`claude-haiku-4-5`** (the lowest cost per question of the
  current models).
- Configurable via `BASE_LEGAL_MODEL`, with **`claude-sonnet-5`** as the
  documented "quality" option.
- Prompt caching on the static system prompt; `max_tokens` capped for answers.
- A published comparison of Haiku 4.5 and Sonnet 5 on the golden set
  (citation validity, refusal accuracy, faithfulness, cost per question) is
  planned as Phase 2 content.

## Consequences
- ➕ Cost per question stays around a fraction of a cent.
  `TODO(verify)` with measured token counts.
- ➖ Haiku may refuse more often or cite less precisely. The comparison will
  show whether the default should change; a change would be a new ADR.
- ➖ Haiku 4.5 uses `budget_tokens`-style extended thinking rather than
  adaptive thinking. Thinking is not needed for this task and stays off by default.
