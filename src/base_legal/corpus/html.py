"""HTML of official publications -> text lines for :class:`StructureParser`.

Planalto's compiled texts mark revoked or superseded wording with
``<strike>`` (sometimes ``<s>``/``<del>``) and keep it in the page next to the
text in force. Everything inside those elements is dropped here, so only the
text in force reaches the parser. Amendment notes such as "(Redação dada pela
Lei nº ...)" are kept; the parser turns them into metadata.

DOU and gov.br pages wrap the act in portal navigation, so each layout names
the element that holds the act; a page without it is rejected rather than
parsed, so menus and footers can never become "law".
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from base_legal.corpus.models import SourceLayout

_STRUCK = ("strike", "s", "del")
_DROP = ("script", "style", "head", "noscript")
_LINE_THROUGH = re.compile(r"text-decoration\s*:\s*[^;]*line-through", re.IGNORECASE)
_BR = "\u2028"  # sentinel for <br>, never present in legal text
_STRUCK_OPEN, _STRUCK_CLOSE = "\ue000", "\ue001"  # private-use sentinels around struck text
_BLOCKS = (
    *("p", "div", "h1", "h2", "h3", "h4", "h5", "h6"),
    *("li", "blockquote", "table", "tr", "td", "th"),
)
_CONTAINERS = {
    SourceLayout.PLANALTO: None,
    SourceLayout.DOU: "div.texto-dou",
    SourceLayout.GOVBR: "#page-document",
}
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_\-]+)""", re.IGNORECASE)


def decode_html(raw: bytes) -> str:
    """Decode using the declared charset; Planalto pages are often windows-1252."""
    match = _META_CHARSET.search(raw[:4096])
    candidates = [match.group(1).decode("ascii")] if match else []
    candidates += ["utf-8", "windows-1252"]
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("windows-1252", errors="replace")


class LayoutError(ValueError):
    """The page does not have the structure expected for its source layout."""


def _prepare(html: str, layout: SourceLayout, *, keep_struck: bool) -> Tag | BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    selector = _CONTAINERS[layout]
    if selector is not None:
        container = soup.select_one(selector)
        if container is None:
            raise LayoutError(f"{layout.value} page has no {selector!r} element")
        soup = BeautifulSoup(str(container), "html.parser")
    for tag_name in _DROP:
        for element in soup.find_all(tag_name):
            element.decompose()
    # Planalto strikes superseded text with <strike> and with inline CSS.
    struck = [*soup.find_all(_STRUCK), *soup.find_all(style=_LINE_THROUGH)]
    for element in struck:
        if not isinstance(element, Tag) or element.decomposed:
            continue
        if keep_struck:
            element.insert_before(_STRUCK_OPEN)
            element.insert_after(_STRUCK_CLOSE)
        else:
            element.decompose()
    # Newlines in the HTML source are just whitespace; only <br> breaks a line.
    for br in soup.find_all("br"):
        br.replace_with(_BR)

    root = soup.body or soup
    # Every block boundary is a line break. Text directly inside a block that
    # also contains nested blocks (common in Planalto, and gov.br headings sit
    # in bare <div>s) keeps its own line instead of being lost or duplicated.
    for block in root.find_all(_BLOCKS):
        if isinstance(block, Tag):
            block.insert_before(_BR)
            block.insert_after(_BR)
    return root


def html_to_lines(html: str, layout: SourceLayout = SourceLayout.PLANALTO) -> list[str]:
    """Return the visible text of each block element, with struck text removed."""
    root = _prepare(html, layout, keep_struck=False)
    # Inline elements are joined without a separator: Planalto splits tokens
    # across spans (e.g. "5<span>7</span>"); source whitespace already
    # separates words.
    lines: list[str] = []
    for part in root.get_text("").split(_BR):
        part = " ".join(part.split())
        if part:
            lines.append(part)
    return lines


def html_to_blocks(
    html: str, layout: SourceLayout = SourceLayout.PLANALTO
) -> list[tuple[str, bool]]:
    """Every line as ``(text, struck)``, including superseded wordings.

    A line is ``struck`` when all of its text is struck (a superseded wording
    of a provision, kept by Planalto before the current one). Words struck
    inside an otherwise current line are dropped, as in :func:`html_to_lines`,
    so the non-struck lines are exactly the lines :func:`html_to_lines` returns.
    """
    root = _prepare(html, layout, keep_struck=True)
    blocks: list[tuple[str, bool]] = []
    depth = 0
    for part in root.get_text("").split(_BR):
        normal: list[str] = []
        struck: list[str] = []
        for char in part:
            if char == _STRUCK_OPEN:
                depth += 1
            elif char == _STRUCK_CLOSE:
                depth = max(depth - 1, 0)
            else:
                (struck if depth else normal).append(char)
        current, old = " ".join("".join(normal).split()), " ".join("".join(struck).split())
        if current:
            blocks.append((current, False))
        elif old:
            blocks.append((old, True))
    return blocks
