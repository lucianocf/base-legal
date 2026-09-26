"""Canonical provision IDs.

Format: ``{doc}:art{N}[:par{N|u}][:inc{ROMAN}][:ali{x}][:item{N}]``

Examples: ``lgpd:art7``, ``lgpd:art7:incIX``, ``lgpd:art11:incII:alig``,
``lgpd:art48:par1:incIII``, ``lgpd:art24:paru``, ``lgpd:art55J:incIV``,
``lgpd:art65:incI-A``.

IDs are part of the public API (ADR 0002): never change this format without a
new ADR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DOC_RE = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_ROMAN_RE = r"[IVXLCDM]+"

ID_RE = re.compile(
    rf"^(?P<doc>{_DOC_RE})"
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

    def __str__(self) -> str:
        parts = [self.doc, f"art{self.article}"]
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
