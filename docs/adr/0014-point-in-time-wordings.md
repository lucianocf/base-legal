# 0014. Point-in-time wordings from the compiled texts

- Status: Proposed
- Date: 2026-09-27

## Context
Phase 3 of the plan asks for point-in-time queries: what did a provision say
on a given date? The LGPD has been amended repeatedly: MP 869/2018, Lei
13.853/2019, Lei 14.010/2020, MP 1.124/2022, Lei 14.460/2022, MP 1.317/2025,
Leis 15.352/2026 and 15.452/2026, among others. The corpus kept only the
current wording.

The compiled text on planalto.gov.br already contains the history. Every
superseded wording stays on the page, struck through, oldest first,
immediately before the current wording, and each carries the note of the
act that introduced it ("Redação dada pela Lei nº 13.853, de 2019"). When
a whole chapter was rewritten (Chapter IX, the ANPD), the older chapter is
kept as one struck block before the current one.

Two alternatives were rejected:
- **Rebuilding versions by applying each amending act** to the original
  text: this interprets amendment instructions, and a single error changes
  the law we show.
- **Asking the model:** never. Legal text is always the official text.

## Decision
- `corpus build` also reads the struck lines (`html_to_blocks`) and writes
  `corpus/history/<doc>.json` for compiled texts. Each provision in force
  that was amended or added gets its wordings, oldest first, the last being
  the current one, each with the act that introduced it (`null` for the
  original text).
- A struck run attaches to the provision right after it only through lines
  with that provision's label. A run that starts with an article is parsed
  as a block of provisions (a rewritten chapter). Runs that fit neither
  rule are ignored, never guessed. Provisions no longer in force get no
  history (limitation).
- **Dates come only from the acts' own pages.** `corpus acts` fetches
  every act linked from an amendment note and records, in
  `corpus/acts.yaml`, the page URL and SHA-256, the DOU publication date and
  the act's own vigência clause (the last one before the signature, so
  quoted clauses of the amended law are skipped). Only "na data de sua
  publicação" and an explicit date become `in_force_from`. Anything else
  stays `null` with a `review` reason:
  - staggered vigência;
  - vetoed parts promulgated later;
  - a note that links to a page whose title is another act (the LGPD page
    names "Lei nº 15.452, de 2026" but links to Lei 15.352's page).
- A wording is valid from its act's in-force date until the next wording's.
  The original wording has no start date: the LGPD's own vigência is
  staggered (art. 65) and is not modeled. Answers built on an undated
  wording are marked `certain: false`.
- The API (`/provisions/{id}?at=AAAA-MM-DD`, `/provisions/{id}/history`),
  the MCP server (`get_provision(at=…)`, `get_provision_history`) and the
  corpus explorer ("Redações anteriores") expose the history. Search and
  answers stay on the current law.

## Consequences
- ➕ Earlier wordings are the official text: extracted, never rewritten.
  Every date is traceable to a hashed page.
- ➕ Uncertainty is explicit instead of silent.
- ➖ Coverage depends on Planalto keeping the struck text: the resolutions
  from gov.br and the DOU have little or no history. Provisions revoked
  since, and the incisos of an old paragraph printed without their
  paragraph, are not covered.
- ➖ The dates are the acts' vigência, not the full legal picture (for
  example an MP's rejection or lapse, or effects deferred by other norms).
  Legal review is recommended before relying on a past wording:
  `TODO(verify)` for each date a user relies on.
