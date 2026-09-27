"""Cross-references inside legal text ("nos termos do inciso II do art. 7º desta Lei").

:func:`find_candidates` is pure: it finds reference phrases in a provision's
text and proposes, for each, the canonical IDs it may denote, most likely
first. :func:`resolve` keeps the first candidate that exists in the index, so
a link is only ever drawn to a provision that is really there.

Reading rules:

- A phrase is a set of levels (article, paragraph or caput, inciso, alínea),
  so both "alínea a do inciso II do art. 7º" and "art. 7º, inciso II" work.
- Levels a phrase omits are borrowed from the citing provision ("§ 1º",
  "inciso II", "caput deste artigo"), unless the phrase names another act.
- A qualifier at the end of an enumeration applies to every item of it
  ("arts. 33, 35, caput e §§ 1º e 2º, e 36 da Lei nº 13.709"), and items
  without an article take the article of the item before them.
- Phrases pointing to acts outside the corpus (the Constitution, codes,
  decrees, other laws) and phrases inside quoted amendment text ("passa a
  vigorar com a seguinte redação: …") produce no link.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from collections.abc import Container, Iterable, Mapping
from dataclasses import dataclass, replace

from base_legal.corpus.ids import (
    ProvisionRef,
    annex_key,
    article_key,
    inciso_key,
    paragraph_key,
    parse_id,
)

# Acts cited by number that are (or may become) part of the corpus.
LAW_IDS = {"13709": "lgpd", "12527": "lai"}

LEVELS = ("art", "par", "inc", "ali")
_CAPUT = "caput"  # the paragraph level set explicitly to the article's caput

_ROMAN = r"(?=[IVXLC])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
_ORD = r"(?:\s*[º°]\.?|o(?![\wà-ú]))?"
_QUOTE_L, _QUOTE_R = "\"“'‘", "\"”'’"
_ITEMS = {
    "art": re.compile(rf"(\d+){_ORD}(?:\s*-\s*([A-Z])\b)?"),
    "par": re.compile(rf"(\d+){_ORD}"),
    "inc": re.compile(rf"({_ROMAN})(?:-([A-Z]))?\b"),
    "ali": re.compile(
        rf"(?:[{_QUOTE_L}]([a-z])[{_QUOTE_R}]"
        r"|([a-z])\b(?=\s*(?:[,;.)]|$|\s+(?:d[oa]s?|n[oa]s?|e|ou|deste|desta)\b)))"
    ),
}
_KEYWORDS = {
    "art": re.compile(r"\barts?\.\s*", re.IGNORECASE),
    "par": re.compile(r"§§?\s*"),
    "inc": re.compile(r"\bincisos?\s+", re.IGNORECASE),
    "ali": re.compile(r"\bal[íi]neas?\s+", re.IGNORECASE),
}
_LIST_SEP = re.compile(r"\s*(?:,|\be\b|\bou\b|\ba\b)\s*")
_SOLE_PARAGRAPH = re.compile(r"\bpar[áa]grafo\s+[úu]nico\b", re.IGNORECASE)
_CAPUT_RE = re.compile(r"\bcaput\b")
_START = re.compile(
    r"\barts?\.|§|\bincisos?\s|\bal[íi]neas?\s|\bpar[áa]grafo\s+[úu]nico\b|\bcaput\b",
    re.IGNORECASE,
)
# between the levels of one phrase: "inciso II do art. 7º", "art. 7º, inciso II"
_CONNECTOR = re.compile(r"\s*,?\s*(?:d[oa]s?|n[oa]s?)\s+|\s*,\s*")
# between the items of an enumeration: "art. 35, caput e §§ 1º e 2º"
_ENUM_SEP = re.compile(r"\s*(?:,\s*(?:e\s+|ou\s+)?|\s+e\s+|\s+ou\s+)")
# tokens that may sit between a phrase and a qualifier shared by an enumeration
_GAP_TOKEN = re.compile(
    r"\s*(?:,|\be\b|\bou\b|\b(?:d|n)[oa]s?\b|\barts?\.|\bcaput\b|§§?|\bincisos?\b|\bal[íi]neas?\b"
    r"|\bconforme\s+o\s+caso\b|\bno\s+que\s+couber\b|\bquando\s+couber\b|\brespectivamente\b"
    rf"|\bpar[áa]grafo\s+[úu]nico\b|\d+{_ORD}(?:-[A-Z]\b)?|{_ROMAN}\b(?:-[A-Z]\b)?"
    rf"|[{_QUOTE_L}][a-z][{_QUOTE_R}])",
    re.IGNORECASE,
)
_QUOTED_AMENDMENT = re.compile(
    r"(?:com\s+as?\s+seguintes?\s+(?:reda[çc][ãa]o|altera[çc][õo]es)"
    r"|acrescid[oa]s?\s+d[oa]s?\s+seguintes?[^:]{0,80})\s*:",
    re.IGNORECASE,
)

_LEAD = r"\s*,?\s+"
_DATE = r"(?:,?\s+de\s+(?:\d{1,2}º?\s+de\s+[a-zç]+\s+de\s+)?(?P<year>\d{4}))?"
_QUALIFIERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "this",
        re.compile(
            _LEAD + r"(?:dest|nest)[ea]\s+"
            r"(?P<what>artigo|par[áa]grafo|Lei|Regulamento|Resolu[çc][ãa]o)\b"
        ),
    ),
    (
        "lgpd",
        re.compile(
            _LEAD + r"(?:d|n)[ao]\s+(?:LGPD\b"
            r"|Lei\s+Geral\s+de\s+Prote[çc][ãa]o\s+de\s+Dados(?:\s+Pessoais)?\b)"
        ),
    ),
    (
        "law",
        re.compile(
            _LEAD + rf"(?:d|n)[ao]\s+Lei\s+n[ºo°.]*\s*(?P<num>\d{{1,3}}(?:\.\d{{3}})+|\d+){_DATE}"
        ),
    ),
    (
        "resolution_annex",
        re.compile(
            _LEAD + r"(?:d|n)o\s+[Aa]nexo(?:\s+(?P<anx>[IVX]+|[ÚU]nico))?"
            rf"\s+da\s+Resolu[çc][ãa]o\s+CD/ANPD\s+n[ºo°.]*\s*(?P<num>\d+){_DATE}"
        ),
    ),
    (
        "resolution",
        re.compile(
            _LEAD + rf"(?:d|n)[ao]\s+Resolu[çc][ãa]o\s+CD/ANPD\s+n[ºo°.]*\s*(?P<num>\d+){_DATE}"
        ),
    ),
    (
        "regulation",
        re.compile(
            _LEAD + r"(?:d|n)[ao]\s+Regulamento\s+(?P<name>(?:[\wà-úÀ-Ú]+\s+){2}[\wà-úÀ-Ú]+)"
        ),
    ),
    (
        "external",
        re.compile(
            _LEAD + r"(?:d|n)[aeo]s?\s+(?:(?:referid|mesm)[oa]\b|Constitui[çc][ãa]o|C[óo]digo|Lei\b"
            r"|Decreto|Medida\s+Provis|[Aa]nexo\b"
            r"|Regimento|Portaria|Instru[çc][ãa]o|Emenda|Resolu[çc][ãa]o|Regulamento|Estatuto"
            r"|Consolida[çc][ãa]o|Conven[çc][ãa]o|Tratado)",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class Candidate:
    """A reference phrase at ``text[start:end]`` and the IDs it may denote, best first."""

    start: int
    end: int
    targets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CrossReference:
    """A resolved link: ``text[start:end]`` refers to the provision ``target``."""

    start: int
    end: int
    target: str


@dataclass(frozen=True, slots=True)
class _Item:
    value: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _Scope:
    """The act (and annex) a phrase points to, and how much it may borrow from ``here``."""

    doc: str
    annexes: tuple[str | None, ...]
    relative: bool
    this_article: bool = False
    this_paragraph: bool = False


_EXTERNAL = object()  # a qualifier naming an act outside the corpus


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def regulation_index(annex_titles: Iterable[tuple[str, str, str]]) -> dict[str, tuple[str, str]]:
    """``(doc, annex, "Anexo — REGULAMENTO DE …")`` rows -> folded title -> (doc, annex)."""
    index: dict[str, tuple[str, str]] = {}
    for doc, annex, title in annex_titles:
        name = fold(title.partition("—")[2] or title)
        if name.startswith("regulamento "):
            index[name] = (doc, annex)
    return index


def _key(level: str, match: re.Match[str]) -> str:
    if level == "art":
        return article_key(match[1], match[2])
    if level == "par":
        return paragraph_key(match[1])
    if level == "inc":
        return inciso_key(match[1], match[2])
    return match[1] or match[2]


def _element(text: str, pos: int) -> tuple[str, list[_Item], int] | None:
    """The element at ``pos``: its level, its items (a list for plurals) and its end."""
    if (m := _SOLE_PARAGRAPH.match(text, pos)) is not None:
        return "par", [_Item(paragraph_key(None), m.start(), m.end())], m.end()
    if (m := _CAPUT_RE.match(text, pos)) is not None:
        return "par", [_Item(_CAPUT, m.start(), m.end())], m.end()
    for level, keyword in _KEYWORDS.items():
        k = keyword.match(text, pos)
        if k is None:
            continue
        word = text[k.start() : k.end()].strip().rstrip(".").lower()
        plural = word == "§§" or word.endswith("s")
        items: list[_Item] = []
        m = _ITEMS[level].match(text, k.end())
        while m is not None:
            items.append(_Item(_key(level, m), m.start(), m.end()))
            sep = _LIST_SEP.match(text, m.end()) if plural else None
            m = _ITEMS[level].match(text, sep.end()) if sep is not None else None
        if not items:
            return None
        items[0] = replace(items[0], start=k.start())
        return level, items, items[-1].end
    return None


def _chain(text: str, pos: int) -> tuple[dict[str, list[_Item]], int]:
    """One phrase from ``pos``: its levels and where it ends (before any qualifier)."""
    chain: dict[str, list[_Item]] = {}
    cursor = pos
    while (element := _element(text, cursor)) is not None:
        level, items, end = element
        if level in chain:
            break
        chain[level] = items
        cursor = end
        connector = _CONNECTOR.match(text, cursor)
        if connector is None:
            break
        following = _element(text, connector.end())
        if following is None or following[0] in chain:
            break
        cursor = connector.end()
    return chain, cursor


_WORD = re.compile(r"[\wà-úÀ-Ú.,()-]+")


def _title_end(text: str, pos: int, title: str) -> int:
    """Where a regulation's title, as cited from ``pos``, ends (it may be abbreviated)."""
    words = title.split()[1:]  # the title without "regulamento"
    end = pos
    for expected in words:
        m = re.compile(r"\s*").match(text, end)
        word = _WORD.match(text, m.end() if m else end)
        if word is None or fold(word.group()).strip(".,") != expected.strip(".,"):
            break
        end = word.end()
    return end


def _qualifier(
    text: str, pos: int, here: ProvisionRef, regulations: Mapping[str, tuple[str, str]]
) -> tuple[_Scope | object | None, int]:
    """A qualifier at ``pos``: a scope, ``_EXTERNAL``, or ``None`` if there is none."""
    for kind, pattern in _QUALIFIERS:
        m = pattern.match(text, pos)
        if m is None:
            continue
        if kind == "this":
            what = fold(m["what"])
            if what == "artigo":
                return _Scope(here.doc, (here.annex,), True, this_article=True), m.end()
            if what == "paragrafo":
                return _Scope(here.doc, (here.annex,), True, this_paragraph=True), m.end()
            if what == "resolucao":
                return _Scope(here.doc, (None,), False), m.end()
            return _Scope(here.doc, (here.annex,), False), m.end()
        if kind == "lgpd":
            return _Scope("lgpd", (None,), False), m.end()
        if kind == "law":
            doc = LAW_IDS.get(m["num"].replace(".", ""))
            return (_Scope(doc, (None,), False) if doc else _EXTERNAL), m.end()
        if kind == "resolution_annex" and m["year"] is not None:
            doc = f"res-anpd-{int(m['num'])}-{m['year']}"
            return _Scope(doc, (annex_key(m["anx"]),), False), m.end()
        if kind == "resolution" and m["year"] is not None:
            doc = f"res-anpd-{int(m['num'])}-{m['year']}"
            return _Scope(doc, (None, "1"), False), m.end()
        if kind == "regulation":
            name = "regulamento " + fold(m["name"])
            found = {(t, v) for t, v in regulations.items() if t.startswith(name)}
            if len({v for _, v in found}) == 1:
                title, (doc, annex) = found.pop()
                return _Scope(doc, (annex,), False), _title_end(text, m.start("name"), title)
        return _EXTERNAL, m.end()
    return None, pos


def _shared_qualifier(
    text: str, pos: int, here: ProvisionRef, regulations: Mapping[str, tuple[str, str]]
) -> _Scope | object | None:
    """A qualifier further on, past only enumeration tokens ("…, 35 e 36 da Lei nº …")."""
    while True:
        scope, _ = _qualifier(text, pos, here, regulations)
        if scope is not None:
            return scope
        token = _GAP_TOKEN.match(text, pos)
        if token is None or token.end() == pos:
            return None
        pos = token.end()


def find_candidates(
    provision_id: str, text: str, regulations: Mapping[str, tuple[str, str]] | None = None
) -> list[Candidate]:
    """Reference phrases in ``text`` (the text of ``provision_id``) and their candidate IDs."""
    here = parse_id(provision_id)
    regulations = regulations or {}
    quoted = _QUOTED_AMENDMENT.search(text)
    limit = quoted.end() if quoted else len(text)
    found: list[Candidate] = []
    previous: tuple[dict[str, list[_Item]], int] | None = None
    pos = 0
    while (start := _START.search(text, pos, limit)) is not None:
        chain, end = _chain(text, start.start())
        if not chain:
            pos = start.end()
            continue
        scope, span_end = _qualifier(text, end, here, regulations)
        if scope is None:  # a qualifier shared by the whole enumeration?
            shared = _shared_qualifier(text, end, here, regulations)
            scope = shared if shared is not None else _Scope(here.doc, (here.annex,), True)
        if "art" not in chain and previous is not None:
            prev_chain, prev_end = previous
            sep = _ENUM_SEP.match(text, prev_end)
            if (
                sep is not None
                and sep.end() == start.start()
                and len(prev_chain.get("art", [])) == 1
            ):
                chain = {"art": prev_chain["art"], **chain}  # "art. 35, caput e §§ 1º e 2º"
                if isinstance(scope, _Scope):
                    scope = replace(scope, relative=False)
        previous = (chain, end)
        pos = max(span_end, start.end())
        if isinstance(scope, _Scope):
            found.extend(_candidates(chain, scope, here, start.start(), span_end))
    return found


def _candidates(
    chain: Mapping[str, list[_Item]], scope: _Scope, here: ProvisionRef, start: int, end: int
) -> list[Candidate]:
    lists = [level for level, items in chain.items() if len(items) > 1]
    if len(lists) > 1:
        return []  # "incisos I e II, alíneas a e b": too ambiguous to link
    fixed = {level: items[0].value for level, items in chain.items()}
    if not lists:
        targets = _targets(fixed, scope, here)
        return [Candidate(start, end, targets)] if targets else []
    level, items = lists[0], chain[lists[0]]
    out: list[Candidate] = []
    for n, item in enumerate(items):
        targets = _targets({**fixed, level: item.value}, scope, here)
        if targets:
            span_start = start if n == 0 else item.start
            span_end = end if n == len(items) - 1 else item.end
            out.append(Candidate(span_start, span_end, targets))
    return out


def _targets(levels: Mapping[str, str], scope: _Scope, here: ProvisionRef) -> tuple[str, ...]:
    top = next(level for level in LEVELS if level in levels)
    article = levels.get("art")
    paragraphs: list[str | None]
    incisos: list[str | None] = [levels.get("inc")]
    if article is None:
        if not scope.relative:
            return ()
        article = here.article
    raw_par = levels.get("par")
    if raw_par == _CAPUT:
        paragraphs = [None]
    elif raw_par is not None:
        paragraphs = [raw_par]
    elif top == "ali" and scope.relative:
        if here.inciso is None:
            return ()
        paragraphs, incisos = [here.paragraph], [here.inciso]
    elif top == "inc" and scope.relative and not scope.this_article:
        # "inciso II" inside a paragraph: that paragraph's inciso, else the caput's
        paragraphs = [here.paragraph, None] if here.paragraph is not None else [None]
        if scope.this_paragraph:
            paragraphs = [here.paragraph]
    else:
        paragraphs = [None]
    out: list[str] = []
    for annex, par, inc in itertools.product(scope.annexes, paragraphs, incisos):
        ref = ProvisionRef(
            doc=scope.doc,
            article=article,
            paragraph=par,
            inciso=inc,
            alinea=levels.get("ali"),
            annex=annex,
        )
        if str(ref) not in out:
            out.append(str(ref))
    return tuple(out)


def resolve(
    source_id: str, candidates: Iterable[Candidate], existing: Container[str]
) -> tuple[CrossReference, ...]:
    """Keep, for each phrase, the first candidate that exists; never a self-link."""
    out: list[CrossReference] = []
    for candidate in candidates:
        for target in candidate.targets:
            if target != source_id and target in existing:
                out.append(CrossReference(candidate.start, candidate.end, target))
                break
    return tuple(out)
