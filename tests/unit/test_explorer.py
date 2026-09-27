import datetime as dt
import json

from base_legal.corpus.history import DocumentHistory, ProvisionHistory, Version
from base_legal.corpus.models import Document, DocumentKind, Provision, ProvisionKind
from base_legal.corpus.xrefs import CrossReference
from base_legal.explorer.site import CSP, build_site, linked_text


def _document(doc: str, *provisions: tuple[str, str, bool]) -> Document:
    return Document(
        id=doc,
        title=f"Ato {doc}",
        kind=DocumentKind.LAW,
        source_url=f"https://example.org/{doc}",
        source_sha256="a" * 64,
        retrieved_at=dt.date(2026, 9, 27),
        redistribution_basis="test",
        provisions=tuple(
            Provision(
                id=pid,
                document_id=doc,
                parent_id=None,
                kind=ProvisionKind.ARTICLE,
                label=pid.split(":art")[1],
                text=text,
                path=("CAPÍTULO I — GERAL", pid.split(":art")[1]),
                ordinal=n,
                revoked=revoked,
            )
            for n, (pid, text, revoked) in enumerate(provisions)
        ),
    )


def test_pages_link_cross_references_across_acts() -> None:
    lgpd = _document(
        "lgpd",
        ("lgpd:art23", "Nos termos do art. 1º da Lei nº 12.527, de 18 de novembro de 2011.", False),
        ("lgpd:art24", "Texto revogado.", True),
    )
    lai = _document("lai", ("lai:art1", "Esta Lei dispõe sobre o acesso.", False))
    files = build_site([lgpd, lai])
    page = files["lgpd.html"]
    assert 'id="lgpd:art23"' in page
    assert '<a class="xref" href="lai.html#lai:art1"' in page
    assert "(revogado)" in page
    assert f'content="{CSP}"' in page
    assert "CAPÍTULO I — GERAL" in page
    search = json.loads(files["search.json"])
    assert {item["id"] for item in search} == {"lgpd:art23", "lai:art1"}  # in force only
    assert '<script src="explorer.js" defer></script>' in files["index.html"]
    assert "innerHTML" not in files["explorer.js"].replace("never innerHTML", "")


def test_corpus_text_is_escaped() -> None:
    hostile = '<script>alert(1)</script> "x" & art. 7º'
    rendered = linked_text(hostile, [CrossReference(40, 47, 'lgpd:art7"><img src=x>')])
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert '"><img' not in rendered


def test_earlier_wordings_are_listed_and_escaped() -> None:
    lgpd = _document("lgpd", ("lgpd:art23", "Redação atual.", False))
    history = DocumentHistory(
        document_id="lgpd",
        source_sha256="a" * 64,
        provisions=(
            ProvisionHistory(
                provision_id="lgpd:art23",
                versions=(
                    Version(text="<b>antiga</b>", introduced_by=None, valid_to=dt.date(2019, 7, 9)),
                    Version(
                        text="Redação atual.",
                        introduced_by="Lei nº 13.853, de 2019",
                        valid_from=dt.date(2019, 7, 9),
                    ),
                ),
            ),
        ),
    )
    page = build_site([lgpd], {"lgpd": history})["lgpd.html"]
    assert "Redações anteriores (1)" in page
    assert "? a 2019-07-09 · texto original" in page
    assert "&lt;b&gt;antiga&lt;/b&gt;" in page
    assert "<b>antiga" not in page
