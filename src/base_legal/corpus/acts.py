"""Amending acts and the dates their wordings came into force (ADR 0014).

Every date comes from the act's own official page on planalto.gov.br: the DOU
publication date ("publicado no DOU de 9.7.2019") and the act's own vigência
clause, the last "Esta Lei / Esta Medida Provisória entra em vigor …" before
the signature. Only two forms are turned into a date: "na data de sua
publicação" (the DOU date) and an explicit "em 17 de março de 2026".
Anything else (staggered vigência, vetoed parts promulgated later) is left
undated and flagged for review, never guessed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

MONTHS = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}  # fmt: skip
_DOU = re.compile(r"publicad[oa] no D\.?O\.?U\.? de (\d{1,2})\.(\d{1,2})\.(\d{4})", re.IGNORECASE)
_VIGENCIA = re.compile(
    r"Est[ae] (?:Lei|Medida Provis[óo]ria)(?: Complementar)?[^.:]{0,120}?"
    r"entra em vigor[^.:]*(?:[.:]|$)"
)
_SIGNATURE = re.compile(r"Bras[íi]lia\s*,\s*\d{1,2}º?\s+de\s+[a-zç]+\s+de\s+\d{4}")
_EXPLICIT = re.compile(r"entra em vigor em (\d{1,2})º? de ([a-zç]+) de (\d{4})")
_ON_PUBLICATION = re.compile(r"entra em vigor na data de sua publica[çc][ãa]o")
_ACT_NOTE = re.compile(
    r"\((?:Reda[çc][ãa]o\s+dada|Inclu[íi]d[oa]|Acrescid[oa])\s+pel[oa]\s+(?P<act>[^()]+?)\s*\)?$",
    re.IGNORECASE,
)


class Act(BaseModel):
    """An amending act, with the provenance of the page its dates come from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    url: str
    retrieved_at: dt.date
    sha256: str
    dou_date: dt.date | None
    vigencia: str | None = Field(description="The act's own vigência clause, verbatim")
    in_force_from: dt.date | None
    review: str | None = Field(default=None, description="Why a date could not be set")


class ActsFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    acts: tuple[Act, ...]

    def by_name(self) -> dict[str, Act]:
        return {a.name: a for a in self.acts}


def _text(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(" ")
    return " ".join(text.replace("\xa0", " ").split())


def act_links(html: str, base_url: str) -> dict[str, str]:
    """Acts named in amendment notes of a compiled page -> the URL each note links to."""
    links: dict[str, str] = {}
    for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        label = " ".join(anchor.get_text(" ").split())
        match = _ACT_NOTE.search(label)
        if match:
            name = " ".join(match["act"].split())
            links.setdefault(name, urljoin(base_url, str(anchor["href"]).split("#")[0]))
    return links


def read_act(html: str) -> tuple[dt.date | None, str | None, dt.date | None, str | None]:
    """DOU date, own vigência clause, in-force date and a review note from an act page."""
    text = _text(html)
    dou = _DOU.search(text)
    dou_date = dt.date(int(dou[3]), int(dou[2]), int(dou[1])) if dou else None
    signature = _SIGNATURE.search(text)
    head = text[: signature.start()] if signature else text
    clauses = list(_VIGENCIA.finditer(head))
    if not clauses:
        return dou_date, None, None, "no vigência clause found before the signature"
    clause = clauses[-1].group(0).strip()
    if clause.endswith(":"):
        return dou_date, clause, None, "staggered vigência: check each provision"
    if _ON_PUBLICATION.search(clause):
        if dou_date is None:
            return None, clause, None, "in force on publication, but no DOU date on the page"
        return dou_date, clause, dou_date, None
    explicit = _EXPLICIT.search(clause)
    if explicit and explicit[2] in MONTHS:
        when = dt.date(int(explicit[3]), MONTHS[explicit[2]], int(explicit[1]))
        return dou_date, clause, when, None
    return dou_date, clause, None, "vigência clause not in a recognized form"


_TITLE = re.compile(
    r"(?:LEI(?: COMPLEMENTAR)?|MEDIDA PROVIS[ÓO]RIA)\s+N[º°o.]*\s*(?P<num>[\d.]+)", re.IGNORECASE
)
_NAME_NUMBER = re.compile(r"n[º°o.]*\s*(?P<num>[\d.]+)", re.IGNORECASE)


def page_matches(name: str, html: str) -> bool:
    """The act page is the act the note names (its title carries the same number)."""
    wanted = _NAME_NUMBER.search(name)
    title = _TITLE.search(_text(html)[:2000])
    if wanted is None or title is None:
        return False
    return wanted["num"].replace(".", "") == title["num"].replace(".", "").rstrip(".")


def describe(name: str, url: str, html: str, data: bytes, today: dt.date) -> Act:
    """An :class:`Act` from its fetched page, or an undated one flagged for review."""
    sha = hashlib.sha256(data).hexdigest()
    if not page_matches(name, html):
        return Act(
            name=name,
            url=url,
            retrieved_at=today,
            sha256=sha,
            dou_date=None,
            vigencia=None,
            in_force_from=None,
            review="the note links to a page whose title is another act: check the source",
        )
    dou_date, vigencia, in_force_from, review = read_act(html)
    return Act(
        name=name,
        url=url,
        retrieved_at=today,
        sha256=sha,
        dou_date=dou_date,
        vigencia=vigencia,
        in_force_from=in_force_from,
        review=review,
    )


def merge(current: Iterable[Act], fetched: Iterable[Act]) -> ActsFile:
    """Newly fetched acts replace those with the same name; order by name."""
    acts = {a.name: a for a in current}
    acts.update({a.name: a for a in fetched})
    return ActsFile(acts=tuple(acts[name] for name in sorted(acts)))
