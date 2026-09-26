"""Citation validation and strict refusal (ADR 0005).

A citation is valid when its provision ID exists in the corpus, the
provision is in force, and the quoted text appears verbatim in that
provision after typographic normalization. An answer passes only if every
citation is valid and every substantive block of text carries at least one
citation.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from base_legal.corpus.ids import is_valid_id
from base_legal.corpus.models import Provision

MIN_QUOTE_CHARS = 10
MIN_SUBSTANTIVE_WORDS = 6

_TRANSLATE = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "°": "º",
        "\xa0": " ",
    }
)


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_TRANSLATE)
    return re.sub(r"\s+", " ", text).strip()


class CitationIssue(StrEnum):
    MALFORMED_ID = "malformed_id"
    UNKNOWN_ID = "unknown_id"
    REVOKED = "revoked"
    VETOED = "vetoed"
    QUOTE_TOO_SHORT = "quote_too_short"
    QUOTE_NOT_FOUND = "quote_not_found"


@dataclass(frozen=True, slots=True)
class Citation:
    provision_id: str
    quote: str


@dataclass(frozen=True, slots=True)
class AnswerBlock:
    """A span of generated text and the citations attached to it."""

    text: str
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class Verdict:
    grounded: bool
    invalid: tuple[tuple[Citation, CitationIssue], ...] = ()
    uncited_blocks: tuple[int, ...] = ()
    reasons: tuple[str, ...] = field(default=())


def check_citation(citation: Citation, corpus: Mapping[str, Provision]) -> CitationIssue | None:
    if not is_valid_id(citation.provision_id):
        return CitationIssue.MALFORMED_ID
    provision = corpus.get(citation.provision_id)
    if provision is None:
        return CitationIssue.UNKNOWN_ID
    if provision.revoked:
        return CitationIssue.REVOKED
    if provision.vetoed:
        return CitationIssue.VETOED
    quote = normalize_for_match(citation.quote).strip(" .;:,\"'")
    if len(quote) < MIN_QUOTE_CHARS:
        return CitationIssue.QUOTE_TOO_SHORT
    if quote not in normalize_for_match(provision.text):
        return CitationIssue.QUOTE_NOT_FOUND
    return None


def is_substantive(text: str) -> bool:
    return len(re.findall(r"\w+", text)) >= MIN_SUBSTANTIVE_WORDS


def judge(blocks: Sequence[AnswerBlock], corpus: Mapping[str, Provision]) -> Verdict:
    """Decide whether an answer may be shown (strict mode)."""
    invalid: list[tuple[Citation, CitationIssue]] = []
    uncited: list[int] = []
    cited_any = False
    for index, block in enumerate(blocks):
        valid_here = 0
        for citation in block.citations:
            issue = check_citation(citation, corpus)
            if issue is None:
                valid_here += 1
            else:
                invalid.append((citation, issue))
        cited_any = cited_any or valid_here > 0
        if valid_here == 0 and is_substantive(block.text):
            uncited.append(index)

    reasons: list[str] = []
    if invalid:
        reasons.append(f"{len(invalid)} invalid citation(s)")
    if uncited:
        reasons.append(f"{len(uncited)} substantive block(s) without a valid citation")
    if not cited_any:
        reasons.append("no valid citation")
    return Verdict(
        grounded=not reasons,
        invalid=tuple(invalid),
        uncited_blocks=tuple(uncited),
        reasons=tuple(reasons),
    )
