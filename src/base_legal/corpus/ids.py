"""Canonical provision IDs.

Format: ``{doc}[:anx{N}]:art{N}[:par{N|u}][:inc{ROMAN}][:ali{x}][:item{N}]``

Examples: ``lgpd:art7``, ``lgpd:art7:incIX``, ``lgpd:art11:incII:alig``,
``lgpd:art48:par1:incIII``, ``lgpd:art24:paru``, ``lgpd:art55J:incIV``,
``lgpd:art65:incI-A``, ``res-anpd-15-2024:anx1:art6`` (art. 6 of the
regulation in the resolution's annex; ADR 0010).

IDs are part of the public API (ADR 0002, ADR 0010): never change this format
without a new ADR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DOC_RE = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_ROMAN_RE = r"[IVXLCDM]+"

ID_RE = re.compile(
    rf"^(?P<doc>{_DOC_RE})"
    r"(?::anx(?P<anx>[1-9]\d*))?"
    r":art(?P<art>\d+[A-Z]*)"
    r"(?::par(?P<par>\d+|u))?"
    rf"(?::inc(?P<inc>{_ROMAN_RE}(?:-[A-Z])?))?"
    r"(?::ali(?P<ali>[a-z]))?"
    r"(?::item(?P<item>\d+))?$"
)


class InvalidProvisionIdError(ValueError):
    """Raised when a string is not a well-formed canonical provision ID."""


@dataclass(frozen=True, slots=True)
class ProvisionRef:
    """Structured form of a canonical provision ID."""

    doc: str
    article: str
    paragraph: str | None = None
    inciso: str | None = None
    alinea: str | None = None
    item: str | None = None
    annex: str | None = None

    def __str__(self) -> str:
        parts = [self.doc]
        if self.annex is not None:
            parts.append(f"anx{self.annex}")
        parts.append(f"art{self.article}")
        if self.paragraph is not None:
            parts.append(f"par{self.paragraph}")
        if self.inciso is not None:
            parts.append(f"inc{self.inciso}")
        if self.alinea is not None:
            parts.append(f"ali{self.alinea}")
        if self.item is not None:
            parts.append(f"item{self.item}")
        return ":".join(parts)


def parse_id(provision_id: str) -> ProvisionRef:
    """Parse a canonical ID, raising :class:`InvalidProvisionIdError` if malformed."""
    match = ID_RE.fullmatch(provision_id)
    if match is None:
        raise InvalidProvisionIdError(provision_id)
    return ProvisionRef(
        doc=match["doc"],
        article=match["art"],
        paragraph=match["par"],
        inciso=match["inc"],
        alinea=match["ali"],
        item=match["item"],
        annex=match["anx"],
    )


def is_valid_id(provision_id: str) -> bool:
    return ID_RE.fullmatch(provision_id) is not None


def validate_doc_id(doc_id: str) -> str:
    if re.fullmatch(_DOC_RE, doc_id) is None:
        raise InvalidProvisionIdError(f"invalid document id: {doc_id!r}")
    return doc_id


def article_key(number: str, suffix: str | None = None) -> str:
    """``("55", "J") -> "55J"``; ``("7", None) -> "7"``."""
    if not number.isdigit():
        raise InvalidProvisionIdError(f"article number must be digits: {number!r}")
    return f"{int(number)}{(suffix or '').upper()}"


def annex_key(roman: str | None) -> str:
    """``None`` / ``"ÚNICO"`` (a single annex) -> ``"1"``; ``"II"`` -> ``"2"``."""
    if roman is None or roman.upper() in {"ÚNICO", "UNICO"}:
        return "1"
    value = _roman_to_int(roman.upper())
    if value is None:
        raise InvalidProvisionIdError(f"annex must be a roman numeral: {roman!r}")
    return str(value)


_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(roman: str) -> int | None:
    if not roman or re.fullmatch(_ROMAN_RE, roman) is None:
        return None
    total = 0
    for current, following in zip(roman, [*roman[1:], ""], strict=True):
        value = _ROMAN_VALUES[current]
        total += -value if following and _ROMAN_VALUES[following] > value else value
    return total


def paragraph_key(number: str | None) -> str:
    """``None`` (parágrafo único) -> ``"u"``; ``"1"`` -> ``"1"``."""
    if number is None:
        return "u"
    if not number.isdigit():
        raise InvalidProvisionIdError(f"paragraph number must be digits: {number!r}")
    return str(int(number))


def inciso_key(roman: str, suffix: str | None = None) -> str:
    """``("I", "A") -> "I-A"``; ``("IX", None) -> "IX"``."""
    roman = roman.upper()
    if re.fullmatch(_ROMAN_RE, roman) is None:
        raise InvalidProvisionIdError(f"inciso must be a roman numeral: {roman!r}")
    return f"{roman}-{suffix.upper()}" if suffix else roman
