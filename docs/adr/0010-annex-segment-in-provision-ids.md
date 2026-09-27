# 0010. Annex segment in canonical provision IDs

- Status: Proposed
- Date: 2026-09-27

## Context
Every CD/ANPD resolution in the corpus has the same shape: a few enacting
articles ("Art. 1º Aprovar o Regulamento … na forma do anexo", sometimes an
article amending another resolution, then "entra em vigor…"), followed by an
**annex containing the regulation itself**, whose articles are numbered from
1 again. Res. CD/ANPD nº 19/2024 has two annexes (the regulation and the
standard contractual clauses).

With the ADR 0002 format (`{doc}:art{N}…`), art. 1 of the resolution and
art. 1 of its regulation would share an ID. ARCHITECTURE §4 already reserved
`res-anpd-19-2024:anx1:…` "to be defined when parsing".

## Decision
- Extend the format with an **optional annex segment** between the document
  and the article: `{doc}[:anx{N}]:art{N}[:par…][:inc…][:ali…][:item…]`.
  `N` is the annex number in Arabic numerals (`ANEXO` alone and `ANEXO
  ÚNICO` are annex 1; `ANEXO II` is annex 2).
  Examples: `res-anpd-15-2024:anx1:art6`, `res-anpd-15-2024:art1`.
- Every existing ID keeps its meaning. The change is additive: all
  previously valid IDs still parse and round-trip.
- The annex heading and title become the first element of the path
  (`Anexo — REGULAMENTO DE COMUNICAÇÃO DE INCIDENTE DE SEGURANÇA > …`).
- Explicit references: "art. 6 da Resolução CD/ANPD nº 15/2024" colloquially
  means art. 6 **of the regulation**, so for resolutions the retriever tries
  `…:anx1:art6` first and then the enacting `…:art6`.

## Consequences
- ➕ IDs stay unique and faithful to the official structure; enacting
  articles (vigência, amendments to other resolutions) remain citable.
- ➕ Additive change, so the IDs in `corpus/lgpd.json` and any stored
  citations remain valid.
- ➖ IDs of regulation articles are longer (`:anx1:`), and golden-set
  entries written as `res-anpd-15-2024:art6` must be updated.
- ➖ The "annex first" rule for explicit references is a heuristic. A
  question that really means an enacting article must say so, or retrieval
  will surface the regulation article first (the enacting article is still
  returned if it is the only match).
