"""Detect explicit legal references in a question ("art. 7º, IX").

Explicit references are resolved as direct ID lookups ahead of the fused
search results (ADR 0004). A reference to a provision that does not exist
("art. 99 da LGPD") is a strong signal to refuse instead of guessing.
"""

from __future__ import annotations

import dataclasses
import re

from base_legal.corpus.ids import ProvisionRef, article_key, inciso_key, paragraph_key

DEFAULT_DOC = "lgpd"

_REF_RE = re.compile(
    r"(?i:\bart(?:igo|\.)?)\s*(?P<art>\d+)\s*(?:º|°|o\b)?(?:\s*-\s*(?P<suf>[A-Z])\b)?"
    r"(?:\s*,?\s*(?:§\s*(?P<par>\d+)\s*(?:º|°)?|(?i:par[áa]grafo)\s+(?:(?P<unico>(?i:[úu]nico))|(?P<parw>\d+))))?"
    r"(?:\s*,?\s*(?i:inciso\s+)?(?P<inc>(?=[IVXLCDM])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})"
    r"(?:IX|IV|V?I{0,3})(?:-[A-Z])?)\b)?"
    r"(?:\s*,?\s*(?:(?i:al[íi]nea)\s+[\"“]?(?P<ali>[a-z])[\"”]?\b|[\"“](?P<ali2>[a-z])[\"”]|(?P<ali3>[a-z])\)))?"
)
_RESOLUTION_RE = re.compile(
    r"(?i:resolu[çc][ãa]o)(?:\s+CD/ANPD)?\s+(?i:n)?[º°o.]*\s*(?P<num>\d+)"
    r"\s*(?:/|,?\s+de\s+(?:\d{1,2}\s+de\s+\w+\s+de\s+)?)(?P<year>\d{4})"
)

_LAI_RE = re.compile(
    r"\bLAI\b|(?i:lei\s+de\s+acesso\s+[àa]\s+informa[çc][ãa]o)"
    r"|(?i:lei)\s+(?i:n)?[º°o.]*\s*12\.?527\b"
)


def _doc_for(question: str) -> str:
    match = _RESOLUTION_RE.search(question)
    if match:
        return f"res-anpd-{int(match['num'])}-{match['year']}"
    if _LAI_RE.search(question):
        return "lai"
    return DEFAULT_DOC


def find_references(question: str) -> list[ProvisionRef]:
    """Return canonical references mentioned in ``question``, in order, deduplicated."""
    doc = _doc_for(question)
    refs: list[ProvisionRef] = []
    for m in _REF_RE.finditer(question):
        paragraph: str | None = None
        if m["par"] or m["parw"]:
            paragraph = paragraph_key(m["par"] or m["parw"])
        elif m["unico"]:
            paragraph = paragraph_key(None)
        inciso = None
        if m["inc"]:
            roman, _, suffix = m["inc"].partition("-")
            inciso = inciso_key(roman, suffix or None)
        ref = ProvisionRef(
            doc=doc,
            article=article_key(m["art"], m["suf"]),
            paragraph=paragraph,
            inciso=inciso,
            alinea=m["ali"] or m["ali2"] or m["ali3"],
        )
        if ref not in refs:
            refs.append(ref)
    return refs


def candidate_ids(ref: ProvisionRef) -> list[str]:
    """Canonical IDs a reference may denote, most likely first.

    "Art. 6 da Resolução CD/ANPD nº 15/2024" colloquially means art. 6 of the
    regulation the resolution approves in its annex (ADR 0010), so for
    resolutions the annex article is tried before the enacting article.
    """
    if ref.annex is None and ref.doc.startswith("res-"):
        return [str(dataclasses.replace(ref, annex="1")), str(ref)]
    return [str(ref)]


# Legal regimes outside the corpus (Brazilian data protection law): foreign laws
# and other Brazilian codes and acts. Named without any act of the corpus, they
# put the question out of scope (strict grounding, ADR 0005).
_OTHER_ACTS = re.compile(
    r"\b(?:GDPR|RGPD|UK\s+GDPR|CCPA|CPRA|HIPAA|PIPEDA|PIPL|COPPA|FERPA"
    r"|Regulamento\s+Geral\s+(?:sobre\s+a|de)\s+Prote[çc][ãa]o\s+de\s+Dados"
    r"|C[óo]digo\s+(?:Penal|Civil|de\s+Processo\s+(?:Penal|Civil)|Tribut[áa]rio"
    r"|de\s+Tr[âa]nsito|de\s+Defesa\s+do\s+Consumidor|Eleitoral)"
    r"|CLT|Consolida[çc][ãa]o\s+das\s+Leis\s+do\s+Trabalho|Constitui[çc][ãa]o(?:\s+Federal)?"
    r"|Marco\s+Civil\s+da\s+Internet|Lei\s+Maria\s+da\s+Penha|Estatuto\s+d[ao]\s+\w+)\b",
    re.IGNORECASE,
)
_CORPUS_ACTS = re.compile(
    r"\bLGPD\b|Lei\s+Geral\s+de\s+Prote[çc][ãa]o\s+de\s+Dados|13\.?709|\bLAI\b"
    r"|Lei\s+de\s+Acesso\s+[àa]\s+Informa[çc][ãa]o|12\.?527|\bANPD\b|Resolu[çc][ãa]o\s+CD/ANPD",
    re.IGNORECASE,
)


def other_acts(question: str) -> list[str]:
    """Acts outside the corpus that ``question`` names, unless it also names one inside."""
    if _CORPUS_ACTS.search(question):
        return []
    return list(dict.fromkeys(" ".join(m.group(0).split()) for m in _OTHER_ACTS.finditer(question)))
