import datetime as dt

from base_legal.corpus.acts import Act, act_links, describe, merge, page_matches, read_act

LAW_PAGE = """<html><body>
<p>LEI Nº 13.853, DE 8 DE JULHO DE 2019</p>
<p>Art. 2º A Lei nº 13.709 passa a vigorar com as seguintes alterações:</p>
<p>"Art. 65. Esta Lei entra em vigor:</p>
<p>I - dia 28 de dezembro de 2018, quanto aos arts. 55-A;" (NR)</p>
<p>Art. 4º Esta Lei entra em vigor na data de sua publicação</p>
<p>Brasília, 8 de julho de 2019; 198º da Independência.</p>
<p>Este texto não substitui o publicado no DOU de 9.7.2019</p>
</body></html>"""


def test_the_acts_own_vigencia_clause_wins_over_quoted_ones() -> None:
    dou, clause, in_force, review = read_act(LAW_PAGE)
    assert dou == dt.date(2019, 7, 9)
    assert clause == "Esta Lei entra em vigor na data de sua publicação"
    assert in_force == dt.date(2019, 7, 9)
    assert review is None


def test_explicit_staggered_and_missing_vigencia() -> None:
    explicit = LAW_PAGE.replace("na data de sua publicação", "em 17 de março de 2026.")
    assert read_act(explicit)[2] == dt.date(2026, 3, 17)
    staggered = LAW_PAGE.replace("na data de sua publicação", "após decorridos:")
    assert read_act(staggered)[2:] == (None, "staggered vigência: check each provision")
    assert read_act("<p>LEI Nº 1</p>")[3] == "no vigência clause found before the signature"


def test_act_links_resolve_relative_urls() -> None:
    html = (
        '<a href="../../_Ato2019-2022/2019/Lei/L13853.htm#art2">(Redação dada pela'
        "\n Lei nº 13.853, de 2019)</a>"
        '<a href="x.htm">(Revogado pela Lei nº 14.460, de 2022)</a>'
    )
    base = "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"
    assert act_links(html, base) == {
        "Lei nº 13.853, de 2019": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/_Ato2019-2022/2019/Lei/L13853.htm"
    }


def test_a_note_linking_to_another_acts_page_is_flagged() -> None:
    # Regression: the LGPD page names "Lei nº 15.452, de 2026" but links to Lei 15.352's page.
    assert page_matches("Lei nº 13.853, de 2019", LAW_PAGE)
    act = describe("Lei nº 15.452, de 2026", "https://x", LAW_PAGE, b"x", dt.date(2026, 9, 27))
    assert act.in_force_from is None
    assert act.review is not None
    assert "another act" in act.review


def test_merge_replaces_by_name_and_sorts() -> None:
    old = Act(
        name="Lei B",
        url="u",
        retrieved_at=dt.date(2026, 1, 1),
        sha256="0",
        dou_date=None,
        vigencia=None,
        in_force_from=None,
    )
    new = old.model_copy(update={"in_force_from": dt.date(2020, 1, 1)})
    other = old.model_copy(update={"name": "Lei A"})
    merged = merge([old], [new, other])
    assert [a.name for a in merged.acts] == ["Lei A", "Lei B"]
    assert merged.by_name()["Lei B"].in_force_from == dt.date(2020, 1, 1)
