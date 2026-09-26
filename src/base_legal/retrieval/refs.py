"""Detect explicit legal references in a question ("art. 7º, IX").

Explicit references are resolved as direct ID lookups ahead of the fused
search results (ADR 0004). A reference to a provision that does not exist
("art. 99 da LGPD") is a strong signal to refuse instead of guessing.
"""

from __future__ import annotations

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


def _doc_for(question: str) -> str:
    match = _RESOLUTION_RE.search(question)
    if match:
        return f"res-anpd-{int(match['num'])}-{match['year']}"
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
