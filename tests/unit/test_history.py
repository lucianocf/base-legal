import datetime as dt

from base_legal.corpus.history import (
    DocumentHistory,
    ProvisionHistory,
    Version,
    date_history,
    extract_history,
    introduced_by,
    label_key,
    version_at,
)
from base_legal.corpus.html import html_to_blocks
from base_legal.corpus.models import Document, DocumentKind
from base_legal.corpus.parser import StructureParser

# Synthetic page in Planalto's style: superseded wordings struck, oldest first.
HTML = """<body>
<p>Art. 5º Para os fins desta Lei, considera-se:</p>
<p><span style="text-decoration:line-through">XIX - autoridade nacional: órgão da administração
pública indireta.</span></p>
<p><strike>XIX - autoridade nacional: órgão da administração pública.
<a href="mpv.htm">(Redação dada pela Medida Provisória nº 869, de 2018)</a></strike></p>
<p>XIX - autoridade nacional: entidade da administração pública.
<a href="l1.htm">(Redação dada pela Lei nº 13.853, de 2019)</a></p>
<p>XX - novo conceito. <a href="l1.htm">(Incluído pela Lei nº 13.853, de 2019)</a></p>
<p><strike>Art. 55-A. Fica criada a autoridade.
(Incluído pela Medida Provisória nº 869, de 2018)</strike></p>
<p><strike>I - primeiro órgão; (Incluído pela Medida Provisória nº 869, de 2018)</strike></p>
<p>CAPÍTULO IX</p>
<p>Art. 55-A. Fica criada a Autoridade Nacional. (Redação dada pela Lei nº 13.853, de 2019)</p>
<p>I - primeiro órgão reformulado; (Redação dada pela Lei nº 13.853, de 2019)</p>
<p>Art. 56. Texto que nunca mudou.</p>
</body>"""

MP, LAW = "Medida Provisória nº 869, de 2018", "Lei nº 13.853, de 2019"


def _history() -> DocumentHistory:
    blocks = html_to_blocks(HTML)
    parser = StructureParser("lgpd")
    provisions = parser.parse([text if not struck else "" for text, struck in blocks])
    document = Document(
        id="lgpd",
        title="LGPD",
        kind=DocumentKind.LAW,
        source_url="https://example.org",
        source_sha256="a" * 64,
        retrieved_at=dt.date(2026, 9, 27),
        redistribution_basis="test",
        provisions=tuple(provisions),
    )
    return extract_history(blocks, document, parser.start_lines)


def test_struck_chains_become_versions_oldest_first() -> None:
    histories = _history().by_id()
    xix = histories["lgpd:art5:incXIX"].versions
    assert [v.introduced_by for v in xix] == [None, MP, LAW]
    assert xix[0].text == "autoridade nacional: órgão da administração pública indireta."
    assert xix[-1].text == "autoridade nacional: entidade da administração pública."
    # a whole struck article block (a chapter rewritten by another act)
    assert [v.introduced_by for v in histories["lgpd:art55A"].versions] == [MP, LAW]
    assert [v.text for v in histories["lgpd:art55A:incI"].versions] == [
        "primeiro órgão;",
        "primeiro órgão reformulado;",
    ]
    # added by a later act: one version; never changed: no history at all
    assert [v.introduced_by for v in histories["lgpd:art5:incXX"].versions] == [LAW]
    assert "lgpd:art56" not in histories


def test_dates_and_point_in_time() -> None:
    acts = {MP: dt.date(2018, 12, 28), LAW: dt.date(2019, 7, 9)}
    histories = date_history(_history(), acts).by_id()
    xix = histories["lgpd:art5:incXIX"]
    assert [(v.valid_from, v.valid_to) for v in xix.versions] == [
        (None, dt.date(2018, 12, 28)),
        (dt.date(2018, 12, 28), dt.date(2019, 7, 9)),
        (dt.date(2019, 7, 9), None),
    ]
    assert version_at(xix, dt.date(2019, 1, 15)) == (xix.versions[1], True)
    assert version_at(xix, dt.date(2020, 1, 1)) == (xix.versions[2], True)
    original, certain = version_at(xix, dt.date(2018, 9, 1))
    assert original is xix.versions[0]
    assert not certain  # the original text's own vigência is not modeled
    xx = histories["lgpd:art5:incXX"]
    assert version_at(xx, dt.date(2019, 1, 1)) == (None, True)  # not yet in force


def test_undated_wordings_make_answers_uncertain() -> None:
    history = ProvisionHistory(
        provision_id="lgpd:art1",
        versions=(
            Version(text="a", introduced_by=None),
            Version(text="b", introduced_by="Lei A", valid_from=dt.date(2019, 1, 1)),
            Version(text="c", introduced_by="Lei B", review="no in-force date for Lei B"),
        ),
    )
    chosen, certain = version_at(history, dt.date(2020, 1, 1))
    assert chosen is not None
    assert chosen.text == "b"
    assert not certain  # Lei B may already have replaced it


def test_helpers() -> None:
    assert introduced_by(["(Vide Lei nº 1)", "(Redação dada pela Lei nº 13.853, de 2019)"]) == LAW
    assert introduced_by(["(Revogado pela Lei nº 14.460, de 2022)"]) is None
    assert [label_key(x) for x in ("Art. 55-A", "§ 1º", "XIX", "Parágrafo único", "Art. 5o")] == [
        "art55a",
        "§1",
        "xix",
        "paru",
        "art5",
    ]
