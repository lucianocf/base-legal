# Legal notice

## Not legal advice

Base Legal is a research tool. Its answers, search results and documentation
are **not legal advice** and do not replace a lawyer or a data protection
officer (encarregado) who knows the facts of a case. Always read the official
text of the provisions cited. Every API response and every answer in the CLI
and the web UI carries this notice.

A verified citation proves that the quoted text exists, verbatim and in force,
in the corpus snapshot. It does **not** prove that the answer interprets that
text correctly (see [THREAT_MODEL.md §6](https://github.com/lucianocf/base-legal/blob/main/docs/THREAT_MODEL.md#6-residual-risks)).

## No affiliation

Base Legal is an independent open-source project. It is **not affiliated
with, endorsed by or connected to** the Autoridade Nacional de Proteção de
Dados (ANPD), the Presidency of the Republic, the Imprensa Nacional or any
other body of the Brazilian government.

## The corpus

The corpus contains official acts, redistributed in normalized form
(provision by provision, with revoked text removed and amendment notes kept
as metadata):

| Act | Source |
|---|---|
| Lei nº 13.709/2018 (LGPD), compiled text | planalto.gov.br |
| Resoluções CD/ANPD nº 1/2021 and nº 2/2022, compiled text | gov.br/anpd |
| Resoluções CD/ANPD nº 4/2023, nº 15/2024 and nº 18/2024 | Diário Oficial da União (in.gov.br) |
| Resolução CD/ANPD nº 19/2024 (Annex I), compiled text | gov.br/anpd |

`corpus/manifest.yaml` records, for each act, the source URL, the retrieval
date and the SHA-256 of the bytes retrieved.

**Basis for redistribution.** Lei nº 9.610/1998, art. 8º, IV: "Não são objeto
de proteção como direitos autorais de que trata esta Lei: […] IV - os textos
de tratados ou convenções, leis, decretos, regulamentos, decisões judiciais e
demais atos oficiais" (checked against the official text at planalto.gov.br
on 2026-09-27). Only the text of the acts is taken from the government
portals; no other portal material (guides, layouts, images) is copied.

**Accuracy.** The corpus is a dated snapshot, parsed automatically and
reviewed against the official pages. It may be outdated or contain parsing
errors. The official publications prevail: the Diário Oficial da União and
the compiled texts at planalto.gov.br and gov.br/anpd.

## Licences of this repository

| Material | Licence |
|---|---|
| Source code | [Apache-2.0](https://github.com/lucianocf/base-legal/blob/main/LICENSE) |
| Evaluation sets (`evals/`) and documentation (`docs/`, READMEs) | CC BY 4.0 |
| Official acts (`corpus/*.json`) | Not protected by copyright (Lei nº 9.610/1998, art. 8º, IV) |

The local query model (voyage-4-nano) is downloaded from its publisher under
the Apache-2.0 licence and is not stored in this repository. The
`voyage-4-large` vectors of the law are not redistributed
([ADR 0009](https://github.com/lucianocf/base-legal/blob/main/docs/adr/0009-no-redistribution-of-voyage-vectors-yet.md)).

## Personal data

Base Legal stores no questions or answers. When you deploy it, you are the
controller (controlador) of any personal data typed into it; see
[PRIVACY.md](https://github.com/lucianocf/base-legal/blob/main/docs/PRIVACY.md).

---

**Resumo em português.** O Base Legal é uma ferramenta de pesquisa e não
constitui aconselhamento jurídico. Não tem vínculo com a ANPD nem com o
governo federal. O corpus reúne atos oficiais, que não são protegidos por
direitos autorais (Lei nº 9.610/1998, art. 8º, IV); prevalecem sempre as
publicações oficiais.
