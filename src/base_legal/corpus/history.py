"""Earlier wordings of each provision, from the official compiled text (ADR 0014).

Planalto keeps every superseded wording of a provision on the compiled page,
struck through and in chronological order, immediately before the current
wording; each carries the note of the act that introduced it ("Redação dada
pela Lei nº 13.853, de 2019"). The first, without a note, is the original
text. This module reads those chains; when each wording was in force comes
from the acts' own publication and vigência (``corpus/acts.yaml``).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import re
import unicodedata
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from base_legal.corpus.models import Document, Provision
from base_legal.corpus.parser import (
    ALI_RE,
    ART_RE,
    INC_RE,
    NOTE_RE,
    PAR_RE,
    TRAILING_VIGENCIA_RE,
    UNICO_RE,
    ParseError,
    StructureParser,
    normalize_text,
)

_LATE_PROMULGATION = re.compile(r"Promulga[çc][ãa]o\s+partes\s+vetadas", re.IGNORECASE)
LATE_PROMULGATION_REVIEW = "vetoed part promulgated later: in-force date not established"
_INTRODUCED = re.compile(
    r"\((?:Reda[çc][ãa]o\s+dada|Inclu[íi]d[oa]|Acrescid[oa])\s+pel[oa]\s+(?P<act>[^()]+?)\s*\)",
    re.IGNORECASE,
)


class Version(BaseModel):
    """One wording of a provision. ``introduced_by`` is ``None`` for the original text.

    ``valid_from`` / ``valid_to`` come from the acts' own pages (``corpus/acts.yaml``);
    ``None`` means not established (the original text's staggered vigência, an act
    whose vigência is not a single date, or a vetoed part promulgated later).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    introduced_by: str | None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    review: str | None = None


class ProvisionHistory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provision_id: str
    versions: tuple[Version, ...]  # oldest first; the last one is the current wording


class DocumentHistory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    source_sha256: str
    provisions: tuple[ProvisionHistory, ...]

    def by_id(self) -> dict[str, ProvisionHistory]:
        return {p.provision_id: p for p in self.provisions}


def introduced_by(notes: Sequence[str]) -> str | None:
    """The act named by the first "Redação dada / Incluído pela …" note, if any."""
    for note in notes:
        match = _INTRODUCED.search(note)
        if match:
            return " ".join(match["act"].split())
    return None


def label_key(label: str) -> str:
    """Comparable form of a provision label: "Art. 55-A" -> "art55a", "§ 1º" -> "§1"."""
    decomposed = unicodedata.normalize("NFKD", label.casefold())
    folded = "".join(c for c in decomposed if not unicodedata.combining(c))
    folded = folded.replace("paragrafo unico", "paru")
    return re.sub(r"[\s.º°o)\-–—:]+|(?<=\d)o\b", "", folded)


def _split(line: str) -> tuple[str, str] | None:
    """A struck line's label and its text without label or notes."""
    for pattern, label in (
        (ART_RE, lambda m: "Art. " + m["num"] + (m["suf"] or "")),
        (PAR_RE, lambda m: "§ " + m["num"]),
        (UNICO_RE, lambda m: "Parágrafo único"),
        (INC_RE, lambda m: m["roman"] + (m["suf"] or "")),
        (ALI_RE, lambda m: m["letter"]),
    ):
        match = pattern.match(line)
        if match:
            rest = TRAILING_VIGENCIA_RE.sub("", NOTE_RE.sub(" ", match["rest"]))
            return label(match), normalize_text(rest).strip()
    return None


def _version(text: str, notes: Sequence[str]) -> Version:
    late = any(_LATE_PROMULGATION.search(n) for n in notes)
    return Version(
        text=text,
        introduced_by=introduced_by(notes),
        review=LATE_PROMULGATION_REVIEW if late else None,
    )


def date_history(history: DocumentHistory, acts: Mapping[str, dt.date | None]) -> DocumentHistory:
    """Set each wording's ``valid_from`` (its act's in-force date) and ``valid_to``."""
    dated: list[ProvisionHistory] = []
    for entry in history.provisions:
        starts: list[dt.date | None] = []
        reviews: list[str | None] = []
        for version in entry.versions:
            if version.introduced_by is None:
                starts.append(None)
                reviews.append(version.review or ORIGINAL_REVIEW)
            elif version.review is not None:
                starts.append(None)
                reviews.append(version.review)
            elif acts.get(version.introduced_by) is None:
                starts.append(None)
                reviews.append(f"no in-force date for {version.introduced_by}")
            else:
                starts.append(acts[version.introduced_by])
                reviews.append(None)
        versions = tuple(
            version.model_copy(
                update={
                    "valid_from": start,
                    "valid_to": starts[n + 1] if n + 1 < len(starts) else None,
                    "review": reviews[n],
                }
            )
            for n, (version, start) in enumerate(zip(entry.versions, starts, strict=True))
        )
        dated.append(entry.model_copy(update={"versions": versions}))
    return history.model_copy(update={"provisions": tuple(dated)})


ORIGINAL_REVIEW = "original wording: in force as provided by the act's own vigência clause"


def version_at(history: ProvisionHistory, when: dt.date) -> tuple[Version | None, bool]:
    """The wording in force on ``when``, and whether that is certain.

    ``None`` means the provision did not exist yet: it was added by an act that
    came into force after ``when``. The latest wording dated on or before
    ``when`` wins; the answer is uncertain if an undated wording follows it (it
    may have replaced it already), if the chosen wording is itself undated, or
    if it is the original text (whose own vigência is not modeled).
    """
    versions = history.versions
    dated = [n for n, v in enumerate(versions) if v.valid_from is not None and v.valid_from <= when]
    if not dated:
        first = versions[0]
        if first.introduced_by is not None and first.valid_from is not None:
            return None, True  # added later: not yet in force on ``when``
        return first, False
    index = dated[-1]
    following = versions[index + 1 :]
    upcoming = next((n for n, v in enumerate(following) if v.valid_from is not None), None)
    between = following if upcoming is None else following[:upcoming]
    chosen = versions[index]
    certain = chosen.review is None and all(v.valid_from is not None for v in between)
    return chosen, certain


def _runs(blocks: Sequence[tuple[str, bool]]) -> list[tuple[int, list[str]]]:
    """Maximal runs of struck lines as (0-based index of the first line, lines)."""
    runs: list[tuple[int, list[str]]] = []
    index = 0
    while index < len(blocks):
        if not blocks[index][1]:
            index += 1
            continue
        first = index
        while index < len(blocks) and blocks[index][1]:
            index += 1
        runs.append((first, [line for line, _ in blocks[first:index]]))
    return runs


def _parse_block(document_id: str, lines: list[str]) -> list[Provision]:
    """A struck block that starts with an article, parsed as a small document.

    A block may hold several successive wordings of the same article; it is
    split wherever a provision repeats, and each part is parsed on its own.
    """
    out: list[Provision] = []
    part: list[str] = []
    for line in [*lines, ""]:
        if line and not (ART_RE.match(line) and any(ART_RE.match(p) for p in part)):
            part.append(line)
            continue
        parser = StructureParser(document_id)
        # not a clean block of provisions: ignore it rather than guess
        with contextlib.suppress(ParseError):
            out += parser.parse(part)
        part = [line] if line else []
    return out


def extract_history(
    blocks: Sequence[tuple[str, bool]],
    document: Document,
    start_lines: Mapping[str, int],
) -> DocumentHistory:
    """Every earlier wording of each provision in force, oldest first.

    ``blocks`` are ``(line, struck)`` pairs and ``start_lines`` the 1-based index,
    in ``blocks``, of each provision's first line. A struck run that starts with
    an article is parsed as a block (a whole chapter rewritten by another act);
    any other run only counts for the provision right after it, and only lines
    with that provision's label.
    """
    current = {p.id: p for p in document.provisions if p.is_normative}
    starts = {line: pid for pid, line in start_lines.items()}
    earlier: dict[str, list[Version]] = {pid: [] for pid in current}
    for first, lines in _runs(blocks):
        structural = next((line for line in lines if _split(line) is not None), None)
        if structural is not None and ART_RE.match(structural):
            for old in _parse_block(document.id, lines):
                if old.id in current and old.text:
                    earlier[old.id].append(_version(old.text, old.amendments))
            continue
        following = starts.get(first + len(lines) + 1)
        if following not in current:
            continue
        for line in lines:
            split = _split(line)
            if split is None or not split[1]:
                continue
            if label_key(split[0]) == label_key(current[following].label):
                earlier[following].append(_version(split[1], NOTE_RE.findall(line)))
    histories = []
    for pid, versions in earlier.items():
        now = _version(current[pid].text, current[pid].amendments)
        if versions or now.introduced_by is not None:  # amended, or added by a later act
            histories.append(ProvisionHistory(provision_id=pid, versions=(*versions, now)))
    return DocumentHistory(
        document_id=document.id,
        source_sha256=document.source_sha256,
        provisions=tuple(histories),
    )
