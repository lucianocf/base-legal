"""Structural parser: lines of a Brazilian legal act -> provision tree.

The parser works on plain text lines (one block element per line), so the
same logic serves the Planalto compiled laws and the ANPD resolutions; the
source-specific HTML handling lives in :mod:`base_legal.corpus.html`.

Recognized structure (Lei Complementar nº 95/1998 conventions):

* headings: ``LIVRO``, ``TÍTULO``, ``CAPÍTULO``, ``Seção``, ``Subseção``
  (optionally followed by a title line);
* rubrics: a short unnumbered line right before an article ("Intimação",
  "Recurso ao Conselho Diretor da ANPD") names the articles that follow; it
  joins their path until the next rubric or heading and is never provision text;
* annexes: ``ANEXO``, ``ANEXO I`` (an ANPD resolution approves a regulation
  "na forma do anexo"); articles after an annex heading get an ``anx{N}``
  segment in their IDs (ADR 0010) and the annex title in their path;
* ``Art. 7º``, ``Art. 10.``, ``Art. 55-J.``;
* ``§ 1º``, ``§ 10.``, ``Parágrafo único.``;
* incisos ``I -``, ``IX –``, ``I-A –``;
* alíneas ``a)``; items ``1.`` (only inside an alínea).

Lines between an opening quote and ``(NR)``/closing quote are amending text
quoted inside a provision (e.g. LGPD art. 60) and are kept as text of the
quoting provision, never parsed as structure.

When a compiled text strikes a revoked provision *including its label*
(Planalto's LGPD art. 55-B; gov.br's Res. CD/ANPD nº 1/2021 annex art. 35,
§ 4º), only its "(Revogado pela …)" note survives, on a line of its own. That
note cannot be tied to a provision ID, so it is dropped rather than attached
to the provision before it, which is still in force.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from base_legal.corpus.ids import annex_key, article_key, inciso_key, paragraph_key
from base_legal.corpus.models import Provision, ProvisionKind

_ROMAN = r"(?=[IVXLCDM])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
_ORD = r"\s*(?:º|°|o(?=\W|$))?"

ART_RE = re.compile(
    rf"^Art\.\s*(?P<num>\d+(?:\s+\d+)*(?=\s*(?:º|°|o\b|\.|-|\s[A-ZÀ-Ú(]))){_ORD}(?:\s*-\s*(?P<suf>[A-Z])\b)?\s*\.?\s*(?P<rest>.*)$"
)
PAR_RE = re.compile(rf"^§\s*(?P<num>\d+){_ORD}\s*\.?\s*(?P<rest>.*)$")
UNICO_RE = re.compile(r"^Par[áa]grafo\s+[úu]nico\s*[.:\-–—]?\s*(?P<rest>.*)$", re.IGNORECASE)
INC_RE = re.compile(rf"^(?P<roman>{_ROMAN})(?:-(?P<suf>[A-Z]))?\s*[-–—]\s*(?P<rest>.+)$")
ALI_RE = re.compile(r"^(?P<letter>[a-z])\)\s*(?P<rest>.+)$")
ITEM_RE = re.compile(r"^(?P<num>\d+)[.)]\s+(?P<rest>.+)$")
HEADING_RE = re.compile(
    rf"^(?P<kind>LIVRO|T[ÍI]TULO|CAP[ÍI]TULO|SE[ÇC][ÃA]O|SUBSE[ÇC][ÃA]O)\s+"
    rf"(?P<num>{_ROMAN}(?:-[A-Z])?|[ÚU]NIC[OA])\b\s*[-–—.]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)
ANNEX_RE = re.compile(rf"^ANEXO(?:\s+(?P<num>{_ROMAN}|[ÚU]NICO))?\b\s*(?:[-–—.]\s*(?P<title>.*))?$")
END_RE = re.compile(
    r"^(Bras[íi]lia\s*,\s|Este (?:texto|conte[úu]do) n[ãa]o substitui)", re.IGNORECASE
)
# Signature blocks of ANPD resolutions ("NOME EM CAIXA ALTA" / "Diretor-Presidente")
# sit between the enacting articles and the annex; they are not provision text.
SIGNATURE_RE = re.compile(r"^[A-ZÀ-Ý][A-ZÀ-Ý'’.-]*(?:\s+[A-ZÀ-Ý'’.-]+)+$")
ROLE_RE = re.compile(r"^Diretor[a]?[- ]Presidente\b", re.IGNORECASE)
# Rows of dots mark elided text in quoted amendments ("Art. 14. ......").
ELISION_RE = re.compile(r"(?:[.…]{4,}\s*)+")
NOTE_RE = re.compile(
    r"\((?:Reda[çc][ãa]o dada|Inclu[íi]d[oa]|Acrescid[oa]|Revogad[oa]|Renumerad[oa]|"
    r"Vide|Vig[êe]ncia|Promulga[çc][ãa]o|Regulamento|Convertid[oa]|Produ[çc][ãa]o de efeitos)"
    r"[^()]*(?:\([^()]*\)[^()]*)*\)",
    re.IGNORECASE,
)
# Planalto links "Vigência" right after an amendment note, outside parentheses.
TRAILING_VIGENCIA_RE = re.compile(r"(?:^|\s)Vig[êe]ncia\s*$", re.IGNORECASE)
VETOED_TEXT_RE = re.compile(r"^\(?\s*VETAD[OA]S?\s*\)?\s*[.;,]?\s*(?:e|ou)?$", re.IGNORECASE)
REVOKED_TEXT_RE = re.compile(r"^\(?\s*revogad[oa]s?\s*\)?\s*[.;]?$", re.IGNORECASE)
OPEN_QUOTE_RE = re.compile(r"^[“\"‘]")
CLOSE_QUOTE_RE = re.compile(r"(?:[”\"’]\s*(?:\(NR\))?|\(NR\))\s*[.;,]?\s*$")

_HEADING_LEVELS = {"LIVRO": 0, "TITULO": 1, "CAPITULO": 2, "SECAO": 3, "SUBSECAO": 4}
_ANNEX_LEVEL = -1
_RUBRIC_LEVEL = 5
MAX_RUBRIC_CHARS = 120


class ParseError(ValueError):
    def __init__(self, line_no: int, line: str, reason: str) -> None:
        super().__init__(f"line {line_no}: {reason}: {line[:120]!r}")
        self.line_no = line_no
        self.line = line
        self.reason = reason


def normalize_text(text: str) -> str:
    """NFC, non-breaking spaces to spaces, collapsed whitespace."""
    text = unicodedata.normalize("NFC", text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


# gov.br sometimes prints a sole paragraph in the same block as its article:
# "Art. 9º … de forma simplificada. Parágrafo único. A ANPD fornecerá …"
_INLINE_SOLE_PARAGRAPH = re.compile(r"(?<=[.;:])\s+(?=Par[áa]grafo\s+[úu]nico\s*[.:–-])")


def split_inline_paragraphs(line: str) -> list[str]:
    """Split a sole paragraph printed inline after its article, outside quoted text."""
    parts: list[str] = []
    start = 0
    for match in _INLINE_SOLE_PARAGRAPH.finditer(line):
        if any(quote in line[: match.start()] for quote in '“"‘'):
            break  # quoted amendment text belongs to the provision that quotes it
        parts.append(line[start : match.start()])
        start = match.end()
    parts.append(line[start:])
    return parts


def _fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text)
    return "".join(c for c in stripped if not unicodedata.combining(c)).upper()


def _is_rubric(line: str, following: str) -> bool:
    return (
        len(line) <= MAX_RUBRIC_CHARS
        and ART_RE.match(following) is not None
        and not line.endswith((".", ";", ":", ",", ")", "”", '"'))
        and NOTE_RE.search(line) is None
        and not OPEN_QUOTE_RE.match(line)
    )


def _is_revocation_note(line: str) -> bool:
    notes = NOTE_RE.findall(line)
    return (
        bool(notes)
        and not NOTE_RE.sub("", line).strip(" .;")
        and all(_fold(n).startswith("(REVOGAD") for n in notes)
    )


def _awaits_revocation(node: _Node | None) -> bool:
    """True if ``node`` has no text of its own yet (label kept, text struck) or says "revogado"."""
    if node is None:
        return False
    text = NOTE_RE.sub(" ", " ".join(node.parts)).strip(" .;")
    return not text or REVOKED_TEXT_RE.match(text) is not None


@dataclass
class _Node:
    id: str
    kind: ProvisionKind
    label: str
    parent_id: str | None
    path: tuple[str, ...]
    ordinal: int
    parts: list[str] = field(default_factory=list)


@dataclass
class _State:
    headings: dict[int, str] = field(default_factory=dict)
    pending_heading: int | None = None
    annex: str | None = None
    article: _Node | None = None
    paragraph: _Node | None = None
    inciso: _Node | None = None
    alinea: _Node | None = None
    last: _Node | None = None
    quoted: bool = False
    ended: bool = False


class StructureParser:
    """Parse the lines of one legal act into :class:`Provision` objects."""

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id

    def parse(self, lines: Iterable[str]) -> list[Provision]:
        state = _State()
        nodes: list[_Node] = []
        seen: set[str] = set()

        def add(node: _Node, line_no: int, line: str) -> _Node:
            if node.id in seen:
                raise ParseError(line_no, line, f"duplicate provision {node.id}")
            seen.add(node.id)
            nodes.append(node)
            state.last = node
            return node

        numbered = [
            (n, part)
            for n, raw in enumerate(lines, start=1)
            for part in split_inline_paragraphs(normalize_text(raw))
            if part
        ]
        for index, (line_no, line) in enumerate(numbered):
            if state.ended:
                break
            following = numbered[index + 1][1] if index + 1 < len(numbered) else ""
            if state.quoted:
                self._append(state, line)
                if CLOSE_QUOTE_RE.search(line):
                    state.quoted = False
                continue
            if OPEN_QUOTE_RE.match(line) and state.last is not None:
                self._append(state, line)
                state.quoted = CLOSE_QUOTE_RE.search(line[1:]) is None
                continue
            if END_RE.match(line):
                state.ended = True
                continue
            if self._annex(state, line) or self._heading(state, line):
                continue

            node = self._structural(state, line, len(nodes))
            if node is not None:
                add(node, line_no, line)
                continue

            if state.pending_heading is not None:
                if NOTE_RE.fullmatch(line):
                    continue  # amendment note between a heading and its title
                level = state.pending_heading
                title = line.strip("’‘'\" ")
                state.headings[level] = f"{state.headings[level]} — {title}"
                state.pending_heading = None
            elif _is_rubric(line, following):
                state.headings[_RUBRIC_LEVEL] = line
                state.last = None
            elif SIGNATURE_RE.match(line) or ROLE_RE.match(line):
                continue  # signature block or a regulation's title in capitals
            elif _is_revocation_note(line) and not _awaits_revocation(state.last):
                continue  # orphan note of a provision struck with its label
            elif state.last is not None:
                self._append(state, line)
            # else: preamble (title, ementa, enacting clause) — not a provision

        return [self._finish(n) for n in nodes]

    # -- structure -----------------------------------------------------------

    def _annex(self, state: _State, line: str) -> bool:
        match = ANNEX_RE.match(line)
        if match is None:
            return False
        state.annex = annex_key(match["num"])
        state.headings.clear()
        state.article = state.paragraph = state.inciso = state.alinea = state.last = None
        label = f"Anexo {match['num']}" if match["num"] else "Anexo"
        title = (match["title"] or "").strip()
        state.headings[_ANNEX_LEVEL] = f"{label} — {title}" if title else label
        state.pending_heading = None if title else _ANNEX_LEVEL
        return True

    def _heading(self, state: _State, line: str) -> bool:
        match = HEADING_RE.match(line)
        if match is None:
            return False
        level = _HEADING_LEVELS[_fold(match["kind"])]
        for deeper in [k for k in state.headings if k >= level]:
            del state.headings[deeper]
        label = f"{match['kind']} {match['num']}"
        title = match["title"].strip()
        state.last = None  # nothing after a heading belongs to the previous provision
        state.headings[level] = f"{label} — {title}" if title else label
        state.pending_heading = None if title else level
        return True

    def _structural(self, state: _State, line: str, ordinal: int) -> _Node | None:
        if m := ART_RE.match(line):
            # Planalto sometimes splits the number across spans ("Art. 5 7.").
            digits = re.sub(r"\s+", "", m["num"])
            key = article_key(digits, m["suf"])
            number = int(digits)
            label = f"Art. {number}{'º' if number < 10 else ''}"
            label += f"-{m['suf']}" if m["suf"] else ""
            headings = tuple(state.headings[k] for k in sorted(state.headings))
            annex = f":anx{state.annex}" if state.annex else ""
            node = _Node(
                id=f"{self.document_id}{annex}:art{key}",
                kind=ProvisionKind.ARTICLE,
                label=label,
                parent_id=None,
                path=(*headings, label),
                ordinal=ordinal,
                parts=[m["rest"]],
            )
            state.article, state.paragraph, state.inciso, state.alinea = node, None, None, None
            state.pending_heading = None
            return node

        if state.article is None:
            return None

        paragraph_match = PAR_RE.match(line)
        unico_match = None if paragraph_match else UNICO_RE.match(line)
        if paragraph_match or unico_match:
            if paragraph_match is not None:
                number = int(paragraph_match["num"])
                key = paragraph_key(paragraph_match["num"])
                label = f"§ {number}{'º' if number < 10 else ''}"
                rest = paragraph_match["rest"]
            elif unico_match is not None:
                key, label, rest = paragraph_key(None), "Parágrafo único", unico_match["rest"]
            else:  # pragma: no cover - guarded by the enclosing condition
                return None
            article = state.article
            node = _Node(
                id=f"{article.id}:par{key}",
                kind=ProvisionKind.PARAGRAPH,
                label=label,
                parent_id=article.id,
                path=(*article.path, label),
                ordinal=ordinal,
                parts=[rest],
            )
            state.paragraph, state.inciso, state.alinea = node, None, None
            return node

        if m := INC_RE.match(line):
            parent = state.paragraph or state.article
            key = inciso_key(m["roman"], m["suf"])
            node = _Node(
                id=f"{parent.id}:inc{key}",
                kind=ProvisionKind.INCISO,
                label=key,
                parent_id=parent.id,
                path=(*parent.path, key),
                ordinal=ordinal,
                parts=[m["rest"]],
            )
            state.inciso, state.alinea = node, None
            return node

        if m := ALI_RE.match(line):
            parent = state.inciso or state.paragraph or state.article
            letter = m["letter"]
            node = _Node(
                id=f"{parent.id}:ali{letter}",
                kind=ProvisionKind.ALINEA,
                label=f"{letter})",
                parent_id=parent.id,
                path=(*parent.path, f"{letter})"),
                ordinal=ordinal,
                parts=[m["rest"]],
            )
            state.alinea = node
            return node

        if state.alinea is not None and (m := ITEM_RE.match(line)):
            parent = state.alinea
            item = str(int(m["num"]))
            return _Node(
                id=f"{parent.id}:item{item}",
                kind=ProvisionKind.ITEM,
                label=f"{item}.",
                parent_id=parent.id,
                path=(*parent.path, f"{item}."),
                ordinal=ordinal,
                parts=[m["rest"]],
            )
        return None

    @staticmethod
    def _append(state: _State, line: str) -> None:
        if state.last is not None:
            state.last.parts.append(line)

    def _finish(self, node: _Node) -> Provision:
        text = normalize_text(ELISION_RE.sub(" (...) ", " ".join(p for p in node.parts if p)))
        amendments = tuple(normalize_text(n) for n in NOTE_RE.findall(text))
        text = normalize_text(NOTE_RE.sub(" ", text))
        if amendments:
            text = TRAILING_VIGENCIA_RE.sub("", text).strip()
        text = re.sub(r"\s+([.;:,])", r"\1", text)
        text = re.sub(r"(?<=[.;])\s*[.;]+$", "", text).strip()
        vetoed = bool(VETOED_TEXT_RE.match(text))
        revoked = bool(REVOKED_TEXT_RE.match(text)) or (
            not text.strip(" .;") and any(_fold(a).startswith("(REVOGAD") for a in amendments)
        )
        return Provision(
            id=node.id,
            document_id=self.document_id,
            parent_id=node.parent_id,
            kind=node.kind,
            label=node.label,
            text="" if revoked or vetoed else text,
            path=node.path,
            amendments=amendments,
            revoked=revoked,
            vetoed=vetoed and not revoked,
            ordinal=node.ordinal,
        )
