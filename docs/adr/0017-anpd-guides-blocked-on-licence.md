# 0017. ANPD guides: not added until their licence is settled

- Status: Proposed
- Date: 2026-09-27

## Context
Phase 3 of the plan adds the ANPD's guides (guias orientativos), with a
section and page citation model, "once licensing is settled". ADR 0007 left a
`TODO(verify)` on the licence the ANPD portal states.

Verified on 2026-09-27 in the pages of gov.br/anpd fetched for the corpus
(footer, linked to <https://creativecommons.org/licenses/by-nd/3.0/deed.pt_BR>):

> "Todo o conteúdo deste site está publicado sob a licença Creative Commons
> Atribuição-SemDerivações 3.0 Não Adaptada"

Official acts (laws, resolutions) are not protected by copyright (Lei nº
9.610/1998, art. 8º, IV), so this licence does not restrict the corpus.
Guides are guidance, not normative acts. Whether art. 8º, IV covers them is
a legal question: `TODO(verify)` with legal review. If it does not, CC BY-ND
3.0 allows verbatim redistribution with attribution but **no derivatives**.
Splitting a guide into chunks, normalizing its text, or quoting it out of
its layout may count as a derivative.

## Decision
- ANPD guides are **not** added to the corpus for now.
- Options for the author, after legal review:
  1. Treat guides as official acts (art. 8º, IV) and add them like the
     resolutions.
  2. Keep them out of the repository. Users fetch the PDFs and index them
     locally (like the Voyage vectors, ADR 0009); only locators (section,
     page) would be committed.
  3. Ask the ANPD for written permission to redistribute normalized text.

## Consequences
- ➕ No redistribution that the licence may forbid.
- ➖ Questions answered only by guidance (not by a norm) stay unanswered or
  are refused.
