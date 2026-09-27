# 0005. Strict grounding: verified citations and refusal

- Status: Proposed
- Date: 2026-09-26

## Context
In the legal domain, a fluent but unsupported answer is worse than no answer
(OWASP LLM09). The project's main promise is that every claim is backed by a
provision and that a machine checks it.

## Decision
1. **Native Claude Citations** with *custom content* documents. The
   retrieved provisions are sent as one document in which **each content
   block is one provision**. Returned `content_block_location` indices map to
   canonical IDs, and `cited_text` comes from the supplied content.
2. **Validator (defense in depth):** for every citation, the ID must exist in
   the corpus and the cited text must be a verbatim substring of that
   provision after normalization (whitespace, quotes, NFC).
3. **Strict refusal (default):** if retrieval scores fall below the threshold,
   or any substantive text block lacks a valid citation, the answer is
   replaced with "No support found in the corpus" plus the nearest provisions
   (text only, nothing generated).
4. **Fallback:** if Citations is unavailable for the chosen model, use
   structured outputs (`output_config.format`) returning
   `{answer, citations[{provision_id, quote}]}` with the same validator. The
   API does not allow Citations and `output_config.format` in the same request.

Checked 2026-09-27: the Citations documentation states that all active
models support citations, `claude-haiku-4-5` included, so the fallback is
not used. How provisions are packaged into documents is refined in
[ADR 0011](0011-one-cited-document-per-provision.md).

## Consequences
- ➕ Hallucinated citations cannot reach the user; the citation-validity metric is 100 % by construction.
- ➕ A crisp README claim that can be shown in a GIF.
- ➖ More refusals, including on some answerable questions. The refusal
  rate is tracked in evals and the threshold tuned on the golden set.
- ➖ Verbatim citation does not prove correct interpretation (see the residual risks in THREAT_MODEL.md).
