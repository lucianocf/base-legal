"""Static corpus explorer for GitHub Pages: one page per act, anchors per provision.

Generated from the committed corpus, with no model and no server: every
provision has an anchor named after its canonical ID
(``lgpd.html#lgpd:art7:incIX``), cross-references are plain links, and a
client-side search reads a JSON index. All corpus text is HTML-escaped here
and rendered with ``textContent`` in the browser; a strict CSP forbids
anything but the site's own script and stylesheet.
"""

from __future__ import annotations

import html
import json
from collections.abc import Iterable, Mapping, Sequence
from importlib import resources

from base_legal.corpus.history import DocumentHistory, ProvisionHistory, Version
from base_legal.corpus.models import Document, Provision
from base_legal.corpus.xrefs import CrossReference, find_candidates, regulation_index, resolve

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self'; base-uri 'none'; form-action 'none'"
)
DISCLAIMER = (
    "O Base Legal é uma ferramenta de pesquisa e não constitui aconselhamento jurídico. "
    "Prevalece sempre o texto oficial publicado."
)
ASSETS = ("explorer.js", "explorer.css")


def _page(title: str, body: Iterable[str], script: bool = False) -> str:
    head = [
        "<!doctype html>",
        '<html lang="pt-BR">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">',
        f"<title>{html.escape(title)}</title>",
        '<link rel="stylesheet" href="explorer.css">',
    ]
    if script:
        head.append('<script src="explorer.js" defer></script>')
    return (
        "\n".join([*head, "</head>", "<body>", "<main>", *body, "</main>", "</body>", "</html>"])
        + "\n"
    )


def linked_text(text: str, references: Sequence[CrossReference]) -> str:
    """Escaped text with each resolved cross-reference as a link to its anchor."""
    out: list[str] = []
    at = 0
    for ref in sorted(references, key=lambda r: r.start):
        if ref.start < at:
            continue
        doc = ref.target.split(":", 1)[0]
        out.append(html.escape(text[at : ref.start]))
        href = html.escape(f"{doc}.html#{ref.target}", quote=True)
        phrase = html.escape(text[ref.start : ref.end])
        out.append(f'<a class="xref" href="{href}" title="{html.escape(ref.target)}">{phrase}</a>')
        at = ref.end
    out.append(html.escape(text[at:]))
    return "".join(out)


def _status(provision: Provision) -> str:
    if provision.vetoed:
        return '<span class="status">(VETADO)</span> '
    if provision.revoked:
        return '<span class="status">(revogado)</span> '
    return ""


def _period(version: Version) -> str:
    start = version.valid_from.isoformat() if version.valid_from else "?"
    end = version.valid_to.isoformat() if version.valid_to else "hoje"
    return f"{start} a {end}"


def _earlier(history: ProvisionHistory | None) -> str:
    """Earlier wordings, oldest first, in a collapsed block (no script needed)."""
    if history is None or len(history.versions) < 2:
        return ""
    items = []
    for version in history.versions[:-1]:
        source = html.escape(version.introduced_by or "texto original")
        items.append(
            f'<li><span class="period">{_period(version)} · {source}</span> '
            f"{html.escape(version.text)}</li>"
        )
    count = len(history.versions) - 1
    return (
        f'<details class="history"><summary>Redações anteriores ({count})</summary>'
        f"<ol>{''.join(items)}</ol></details>"
    )


def _document_page(
    document: Document,
    references: Mapping[str, Sequence[CrossReference]],
    histories: Mapping[str, ProvisionHistory],
) -> str:
    body = [
        '<p class="nav"><a href="index.html">← Todos os atos</a></p>',
        f"<h1>{html.escape(document.title)}</h1>",
        '<p class="source">Fonte oficial: '
        f'<a href="{html.escape(document.source_url, quote=True)}" rel="noopener">'
        f"{html.escape(document.source_url)}</a> · obtido em {document.retrieved_at}</p>",
        f'<p class="disclaimer">{DISCLAIMER}</p>',
    ]
    shown: tuple[str, ...] = ()
    for provision in document.provisions:
        headings = _headings(provision)
        common = 0
        while common < min(len(shown), len(headings)) and shown[common] == headings[common]:
            common += 1
        for level, heading in enumerate(headings[common:], start=common):
            tag = f"h{min(level + 2, 6)}"
            body.append(f'<{tag} class="heading">{html.escape(heading)}</{tag}>')
        shown = headings
        depth = _levels(provision) - 1
        classes = f"provision {provision.kind.value} depth{min(depth, 4)}"
        if not provision.is_normative:
            classes += " inactive"
        anchor = html.escape(provision.id, quote=True)
        label = html.escape(provision.label)
        text = linked_text(provision.text, references.get(provision.id, ()))
        body.append(
            f'<p class="{classes}" id="{anchor}">'
            f'<a class="label" href="#{anchor}" title="{anchor}">{label}</a> '
            f"{_status(provision)}{text}</p>"
        )
        earlier = _earlier(histories.get(provision.id))
        if earlier:
            body.append(earlier)
    return _page(document.title, body)


def _levels(provision: Provision) -> int:
    """Article, paragraph, inciso, alínea and item levels in the ID (not doc or annex)."""
    return sum(1 for part in provision.id.split(":")[1:] if not part.startswith("anx"))


def _headings(provision: Provision) -> tuple[str, ...]:
    """Chapter, section and annex headings: the path without the provision's label chain."""
    return provision.path[: len(provision.path) - _levels(provision)]


def build_site(
    documents: Sequence[Document], histories: Mapping[str, DocumentHistory] | None = None
) -> dict[str, str]:
    """Relative path -> file content for the whole explorer."""
    existing = {p.id for d in documents for p in d.provisions if p.is_normative}
    regulations = regulation_index(
        (d.id, p.id.split(":")[1][3:], p.path[0])
        for d in documents
        for p in d.provisions
        if p.id.split(":")[1].startswith("anx") and p.path
    )
    files: dict[str, str] = {}
    index_rows = []
    search: list[dict[str, str]] = []
    for document in documents:
        references = {
            p.id: resolve(p.id, find_candidates(p.id, p.text, regulations), existing)
            for p in document.provisions
            if p.is_normative
        }
        history = (histories or {}).get(document.id)
        by_id = history.by_id() if history is not None else {}
        files[f"{document.id}.html"] = _document_page(document, references, by_id)
        in_force = len(document.in_force())
        index_rows.append(
            f'<li><a href="{document.id}.html">{html.escape(document.title)}</a> '
            f'<span class="count">{in_force} dispositivos em vigor</span></li>'
        )
        search += [
            {"id": p.id, "path": " > ".join(p.path), "text": p.text}
            for p in document.provisions
            if p.is_normative
        ]
    files["index.html"] = _page(
        "Base Legal — explorador do corpus",
        [
            "<h1>Explorador do corpus</h1>",
            "<p>Texto oficial, dispositivo por dispositivo, com o identificador canônico de "
            "cada um e as remissões como links. Sem modelo de linguagem e sem servidor.</p>",
            f'<p class="disclaimer">{DISCLAIMER}</p>',
            '<form id="search" role="search"><label for="q">Buscar no texto</label>'
            '<input id="q" type="search" autocomplete="off" maxlength="200"></form>',
            '<p id="status" aria-live="polite"></p><ol id="results"></ol>',
            "<h2>Atos</h2>",
            '<ul class="acts">',
            *index_rows,
            "</ul>",
        ],
        script=True,
    )
    files["search.json"] = json.dumps(search, ensure_ascii=False, separators=(",", ":"))
    static = resources.files("base_legal.explorer") / "static"
    for name in ASSETS:
        files[name] = (static / name).read_text(encoding="utf-8")
    return files
