"""HTML of official publications -> text lines for :class:`StructureParser`.

Planalto's compiled texts mark revoked or superseded wording with
``<strike>`` (sometimes ``<s>``/``<del>``) and keep it in the page next to the
text in force. Everything inside those elements is dropped here, so only the
text in force reaches the parser. Amendment notes such as "(Redação dada pela
Lei nº ...)" are kept; the parser turns them into metadata.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

_STRUCK = ("strike", "s", "del")
_DROP = ("script", "style", "head", "noscript")
_LINE_THROUGH = re.compile(r"text-decoration\s*:\s*[^;]*line-through", re.IGNORECASE)
_BR = "\u2028"  # sentinel for <br>, never present in legal text
_BLOCKS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote")
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


def html_to_lines(html: str) -> list[str]:
    """Return the visible text of each block element, with struck text removed."""
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in (*_DROP, *_STRUCK):
        for element in soup.find_all(tag_name):
            element.decompose()
    # Planalto also strikes superseded text with inline CSS.
    for element in soup.find_all(style=_LINE_THROUGH):
        if isinstance(element, Tag) and not element.decomposed:
            element.decompose()
    # Newlines in the HTML source are just whitespace; only <br> breaks a line.
    for br in soup.find_all("br"):
        br.replace_with(_BR)

    root = soup.body or soup
    blocks = [b for b in root.find_all(_BLOCKS) if isinstance(b, Tag)]
    # Keep only innermost blocks, so nested <p> (common in Planalto) is not duplicated.
    leaves = [b for b in blocks if b.find(_BLOCKS) is None]
    if not leaves:
        return [line for line in root.get_text("\n").splitlines() if line.strip()]

    lines: list[str] = []
    for block in leaves:
        # Inline elements are joined without a separator: Planalto splits
        # tokens across spans (e.g. "5<span>7</span>"); source whitespace
        # already separates words.
        for part in block.get_text("").split(_BR):
            part = " ".join(part.split())
            if part:
                lines.append(part)
    return lines
