# 0007. Licensing: code, data and corpus

- Status: Proposed
- Date: 2026-09-26

## Context
Three kinds of material live in the repo: our code, our data and docs (eval
sets, documentation), and third-party legal texts. The project must be
impeccable here, because its author is a data protection and digital law professional.

## Decision
- **Code:** Apache-2.0. It is permissive, carries an explicit patent grant
  and is accepted by enterprises and clients.
- **Eval sets and documentation:** CC BY 4.0.
- **Laws and resolutions:** redistributed in normalized form. **Basis:** Lei
  nº 9.610/1998, art. 8º, IV: texts of treaties, laws, decrees, regulations,
  judicial decisions and other official acts are not protected by copyright.
  The source URL, retrieval date and hash are recorded in `manifest.yaml`.
- **ANPD guides and other gov.br publications** (not in the MVP): **not
  redistributed**. A script downloads them from the official source. gov.br
  portals commonly license content under CC BY-ND 3.0 (the Arquivo Nacional
  portal states this explicitly), and the *NoDerivatives* term conflicts with
  redistributing chunked or normalized versions. `TODO(verify)`: the license
  stated on the ANPD portal itself, before Phase 3.
- A `LEGAL_NOTICE.md` explains all of the above, says the project has no
  affiliation with or endorsement by the ANPD or the Brazilian government,
  and states that nothing here is legal advice.

## Consequences
- ➕ Reproducible CI and evals (the corpus is in the repo) without copyright risk.
- ➕ The legal reasoning itself becomes a visible, credible artifact.
- ➖ Guides need a download step and can't be part of deterministic CI unless the licensing is clarified.
