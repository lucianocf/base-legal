from pathlib import Path

import pytest

from base_legal.corpus.html import decode_html, html_to_lines
from base_legal.corpus.models import Provision, ProvisionKind
from base_legal.corpus.parser import ParseError, StructureParser, normalize_text


@pytest.fixture
def provisions(fixtures_dir: Path) -> dict[str, Provision]:
    raw = (fixtures_dir / "planalto_synthetic.html").read_bytes()
    lines = html_to_lines(decode_html(raw))
    return {p.id: p for p in StructureParser("lgpd").parse(lines)}


def test_decodes_windows_1252(fixtures_dir: Path) -> None:
    text = decode_html((fixtures_dir / "planalto_synthetic.html").read_bytes())
    assert "Lei Geral de Proteção de Dados Pessoais" in text


def test_article_caput_and_label(provisions: dict[str, Provision]) -> None:
    art1 = provisions["lgpd:art1"]
    assert art1.kind is ProvisionKind.ARTICLE
    assert art1.label == "Art. 1º"
    assert art1.text.startswith("Esta Lei dispõe sobre o tratamento de dados pessoais")
    assert art1.parent_id is None


def test_hierarchy_path_from_headings(provisions: dict[str, Provision]) -> None:
    assert provisions["lgpd:art7:incIX"].path == (
        "CAPÍTULO II — DO TRATAMENTO DE DADOS PESSOAIS",
        "Seção I — Dos Requisitos para o Tratamento de Dados Pessoais",
        "Art. 7º",
        "IX",
    )
    # A new chapter resets the section.
    assert provisions["lgpd:art24"].path[:-1] == (
        "CAPÍTULO IV — DO TRATAMENTO DE DADOS PESSOAIS PELO PODER PÚBLICO",
    )


def test_struck_text_is_dropped_and_notes_become_metadata(
    provisions: dict[str, Provision],
) -> None:
    unico = provisions["lgpd:art1:paru"]
    assert unico.text == "As normas gerais contidas nesta Lei são de interesse nacional."
    assert unico.amendments == ("(Incluído pela Lei nº 13.853, de 2019)",)
    assert all("Texto antigo" not in p.text for p in provisions.values())


def test_revoked_provision_is_flagged(provisions: dict[str, Provision]) -> None:
    par1 = provisions["lgpd:art7:par1"]
    assert par1.revoked
    assert par1.text == ""
    assert not provisions["lgpd:art7:par3"].revoked


def test_incisos_attach_to_article_or_paragraph(provisions: dict[str, Provision]) -> None:
    assert provisions["lgpd:art5:incVIII"].parent_id == "lgpd:art5"
    inc = provisions["lgpd:art48:par1:incIII"]
    assert inc.parent_id == "lgpd:art48:par1"
    assert inc.text == "a indicação das medidas técnicas e de segurança utilizadas;"


def test_alineas(provisions: dict[str, Provision]) -> None:
    alinea = provisions["lgpd:art11:incII:alig"]
    assert alinea.kind is ProvisionKind.ALINEA
    assert alinea.label == "g)"
    assert alinea.parent_id == "lgpd:art11:incII"


def test_article_numbers_ten_and_up_and_suffixes(provisions: dict[str, Provision]) -> None:
    assert provisions["lgpd:art10"].label == "Art. 10"
    art = provisions["lgpd:art55A"]
    assert art.label == "Art. 55-A"
    assert art.text == "Fica criada a Autoridade Nacional de Proteção de Dados (ANPD)."


def test_inciso_with_suffix(provisions: dict[str, Provision]) -> None:
    inc = provisions["lgpd:art65:incI-A"]
    assert inc.label == "I-A"
    assert inc.text.startswith("dia 1º de agosto de 2021")
    assert inc.amendments == ("(Incluído pela Lei nº 14.010, de 2020)",)


def test_quoted_amending_text_is_not_parsed_as_structure(
    provisions: dict[str, Provision],
) -> None:
    assert "lgpd:art60:incX" not in provisions
    assert "exclusão definitiva" in provisions["lgpd:art60"].text
    assert provisions["lgpd:art65"].parent_id is None


def test_stops_at_signature_block(provisions: dict[str, Provision]) -> None:
    assert all("MICHEL TEMER" not in p.text for p in provisions.values())
    assert "Brasília" not in provisions["lgpd:art65:incI-A"].text


def test_preamble_is_not_a_provision(provisions: dict[str, Provision]) -> None:
    assert all("PRESIDENTE DA REPÚBLICA" not in p.text for p in provisions.values())


def test_ordinals_follow_document_order(provisions: dict[str, Provision]) -> None:
    ordinals = [p.ordinal for p in provisions.values()]
    assert ordinals == sorted(ordinals)
    assert provisions["lgpd:art1"].ordinal == 0


def test_duplicate_provision_raises() -> None:
    lines = ["Art. 1º Primeiro.", "Art. 1º De novo."]
    with pytest.raises(ParseError, match="duplicate provision lgpd:art1"):
        StructureParser("lgpd").parse(lines)


def test_normalize_text() -> None:
    assert normalize_text(" a\xa0\n b\t c ") == "a b c"


def test_ordinal_variants() -> None:
    parsed = StructureParser("x").parse(["Art. 2o Texto.", "§ 2° Outro.", "Art. 3 ° Mais."])
    assert [p.id for p in parsed] == ["x:art2", "x:art2:par2", "x:art3"]


def test_continuation_lines_are_joined() -> None:
    parsed = StructureParser("x").parse(["Art. 1º Começo do texto", "e continuação."])
    assert parsed[0].text == "Começo do texto e continuação."


def test_css_line_through_is_treated_as_struck_text() -> None:
    # Real layout from the Planalto compiled LGPD (art. 4, II, b): the old wording
    # is struck with inline CSS, an intermediate one with <strike>.
    html = """
    <p>Art. 4º Esta Lei não se aplica ao tratamento de dados pessoais:</p>
    <p>II - realizado para fins exclusivamente:</p>
    <p><span style="color: black; text-decoration:line-through">
      b) acadêmicos, aplicando-se a esta hipótese os arts. 7º e 11 desta Lei;</span></p>
    <p><strike><span>b) acadêmicos; (Redação dada pela Medida Provisória nº 869, de 2018)</span>
    </strike></p>
    <p><span>b) acadêmicos, aplicando-se a esta hipótese os arts. 7º e 11 desta Lei;</span></p>
    """
    provisions = {p.id: p for p in StructureParser("lgpd").parse(html_to_lines(html))}
    assert provisions["lgpd:art4:incII:alib"].text == (
        "acadêmicos, aplicando-se a esta hipótese os arts. 7º e 11 desta Lei;"
    )


def test_source_newlines_do_not_split_lines_but_br_does() -> None:
    html = "<p>Art. 5<span>7</span>. (VETADO).</p><p>Art. 58.\n Primeira linha<br>§ 1º Segunda.</p>"
    assert html_to_lines(html) == ["Art. 57. (VETADO).", "Art. 58. Primeira linha", "§ 1º Segunda."]


def test_article_number_split_across_spans() -> None:
    # Real case: art. 57 of the Planalto compiled LGPD is "Art. 5<span>\n7.</span>".
    parsed = StructureParser("lgpd").parse(["Art. 5 7. (VETADO).", "Art. 7º O tratamento 2 vezes."])
    assert [p.id for p in parsed] == ["lgpd:art57", "lgpd:art7"]
    assert parsed[1].text == "O tratamento 2 vezes."


def test_real_planalto_note_quirks() -> None:
    # Real lines from the Planalto compiled LGPD.
    parsed = {
        p.id: p
        for p in StructureParser("lgpd").parse(
            [
                "Art. 7º O tratamento de dados pessoais somente poderá ser realizado:",
                "§ 2º (Revogado). (Redação dada pela Lei nº 13.853, de 2019) Vigência",
                "§ 3º (VETADO). (Incluído pela Lei nº 13.853, de 2019) Vigência",
                "§ 4º Texto em vigor. (Redação dada pela Lei nº 13.853, de 2019) Vigência",
                "Art. 65. Esta Lei entra em vigor:",
                "I-A – dia 1º de agosto de 2021, quanto aos arts. 52, 53 e 54; "
                "(Incluído pela Lei nº 14.010, de 2020) (Convertida na Lei nº 14.058, de 2020)",
            ]
        )
    }
    assert parsed["lgpd:art7:par2"].revoked
    assert parsed["lgpd:art7:par3"].vetoed
    assert parsed["lgpd:art7:par3"].text == ""
    assert not parsed["lgpd:art7:par3"].is_normative
    assert parsed["lgpd:art7:par4"].text == "Texto em vigor."
    inc = parsed["lgpd:art65:incI-A"]
    assert inc.text == "dia 1º de agosto de 2021, quanto aos arts. 52, 53 e 54;"
    assert "(Convertida na Lei nº 14.058, de 2020)" in inc.amendments


def test_heading_with_amendment_note_and_signature_block() -> None:
    # Real layout from the Planalto compiled LGPD (chapter IX and the closing lines).
    parsed = StructureParser("lgpd").parse(
        [
            "Art. 54. Texto do artigo.",
            "CAPÍTULO IX",
            "(Redação dada pela Lei nº 15.352, de 2026)",
            "DA AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS’",
            "Art. 55-A. Texto do novo artigo.",
            "Brasília , 14 de agosto de 2018; 197º da Independência e 130º da República.",
            "MICHEL TEMER",
        ]
    )
    art54, art55a = parsed
    assert art54.text == "Texto do artigo."
    assert art55a.path == ("CAPÍTULO IX — DA AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS", "Art. 55-A")
    assert art55a.text == "Texto do novo artigo."
