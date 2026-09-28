# 0016. Refuse questions that name only acts outside the corpus

- Status: Proposed
- Date: 2026-09-27

## Context
Strict grounding (ADR 0005) refuses when retrieval finds nothing close
enough: the best dense similarity must reach 0.40. Out-of-corpus questions
in the right domain get through anyway. On 2026-09-27 these scored:

| Question | Best dense similarity |
|---|---|
| "multa máxima do GDPR" | 0.62 |
| "direitos do consumidor na CCPA" | 0.46 |
| "pena de furto no Código Penal" | 0.43 |

The lowest-scoring answerable question is at 0.48, so no threshold separates
the two groups. Must-refuse accuracy was 66.7 %. The local reranker
(ADR 0015) did not separate them either.

A related bug: "O que diz o art. 5º da Constituição?" resolved "art. 5º"
against the default document, the LGPD, and answered with LGPD art. 5º as
an explicit reference.

## Decision
- `other_acts(question)` detects named legal regimes outside the corpus:
  - foreign data protection laws (GDPR/RGPD, CCPA/CPRA, HIPAA, PIPEDA, PIPL…);
  - other Brazilian codes and acts (Código Penal, Civil, de Processo,
    Tributário, de Trânsito, de Defesa do Consumidor, Eleitoral; CLT; the
    Constitution; the Marco Civil da Internet; the Lei Maria da Penha;
    "Estatuto de/do …").

  It applies only when the question names **no** act of the corpus (LGPD,
  LAI, ANPD, a CD/ANPD resolution). "A LGPD difere do GDPR?" still gets an
  answer.
- Such a question is refused as `out_of_scope` before any model call.
  Explicit references are not resolved against the default document, and
  the nearest provisions are still shown. Explicit references that do
  resolve (none, in that case) and nonexistent provisions keep their
  precedence.
- The CI eval gate for must-refuse accuracy rises from 0.6 to 0.85.

## Consequences
- ➕ Must-refuse accuracy: 100 % on dev and holdout (was 60 % / 75 %), with
  no false refusals and unchanged recall.
- ➖ **The holdout confirmation is not blind.** The rule was written after
  reading every must-refuse question, including the holdout's GDPR one.
  Re-measure it on new questions once the golden set is validated.
- ➖ A question about another act that the corpus touches (for example
  "o GDPR vale no Brasil?", which LGPD art. 3º bears on) is refused rather
  than answered. Strict grounding prefers that; the refusal lists the
  nearest provisions.
- ➖ The list of regimes is a closed list; unknown acts fall back to the
  similarity threshold.
