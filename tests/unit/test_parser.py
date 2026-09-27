from pathlib import Path

import pytest

from base_legal.corpus.html import LayoutError, decode_html, html_to_lines
from base_legal.corpus.models import Provision, ProvisionKind, SourceLayout
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


# -- ANPD resolutions: real excerpts from the DOU and gov.br layouts ---------


def _parse_fixture(
    fixtures_dir: Path, name: str, layout: SourceLayout, doc: str
) -> dict[str, Provision]:
    lines = html_to_lines(decode_html((fixtures_dir / name).read_bytes()), layout)
    return {p.id: p for p in StructureParser(doc).parse(lines)}


@pytest.fixture
def res15(fixtures_dir: Path) -> dict[str, Provision]:
    return _parse_fixture(
        fixtures_dir, "dou_res_15_2024_excerpt.html", SourceLayout.DOU, "res-anpd-15-2024"
    )


@pytest.fixture
def res1(fixtures_dir: Path) -> dict[str, Provision]:
    return _parse_fixture(
        fixtures_dir, "govbr_res_1_2021_excerpt.html", SourceLayout.GOVBR, "res-anpd-1-2021"
    )


def test_portal_chrome_is_never_parsed(
    res15: dict[str, Provision], res1: dict[str, Provision]
) -> None:
    for provisions in (res15, res1):
        assert not any(":art99" in pid or ":art100" in pid for pid in provisions)
        assert all("REDES SOCIAIS" not in p.text for p in provisions.values())


def test_missing_layout_container_is_rejected(fixtures_dir: Path) -> None:
    html = (fixtures_dir / "planalto_synthetic.html").read_bytes()
    with pytest.raises(LayoutError, match="texto-dou"):
        html_to_lines(decode_html(html), SourceLayout.DOU)


def test_enacting_articles_and_annex_regulation_get_distinct_ids(
    res15: dict[str, Provision],
) -> None:
    assert res15["res-anpd-15-2024:art1"].text.startswith("Aprovar o Regulamento")
    assert res15["res-anpd-15-2024:art1"].path == ("Art. 1º",)
    annex_art1 = res15["res-anpd-15-2024:anx1:art1"]
    assert annex_art1.text.startswith("Este Regulamento tem por objetivo")
    assert annex_art1.path[:2] == (
        "Anexo — REGULAMENTO DE COMUNICAÇÃO DE INCIDENTE DE SEGURANÇA",
        "CAPÍTULO I — DISPOSIÇÕES PRELIMINARES",
    )


def test_signature_block_is_not_provision_text(res15: dict[str, Provision]) -> None:
    art3 = res15["res-anpd-15-2024:art3"]
    assert art3.text == "Esta Resolução entra em vigor na data da sua publicação."


def test_quoted_amendment_with_elided_rows(res15: dict[str, Provision]) -> None:
    art2 = res15["res-anpd-15-2024:art2"]
    assert '"Art. 14. (...) II - no caso da comunicação' in art2.text
    assert "...." not in art2.text
    assert "res-anpd-15-2024:art14" not in res15  # quoted text is not structure


def test_incident_deadline_article(res15: dict[str, Provision]) -> None:
    art6 = res15["res-anpd-15-2024:anx1:art6"]
    assert "no prazo de três dias úteis" in art6.text
    assert res15["res-anpd-15-2024:anx1:art6:par2:incXII"].parent_id == (
        "res-anpd-15-2024:anx1:art6:par2"
    )


def test_govbr_struck_text_notes_and_div_headings(res1: dict[str, Provision]) -> None:
    # <del>Parágrafo único…</del> was renumbered to § 1º by Res. 4/2023.
    assert "res-anpd-1-2021:anx1:art32:paru" not in res1
    par1 = res1["res-anpd-1-2021:anx1:art32:par1"]
    assert par1.amendments == (
        "(Redação dada pela Resolução CD/ANPD nº 4, de 24 de fevereiro de 2023)",
    )
    assert par1.text.endswith("se compatíveis com o disposto nos arts. 30 e 31.")
    # Chapter and section titles live in bare <div>s on gov.br.
    assert res1["res-anpd-1-2021:anx1:art33"].path[-3:] == (
        "CAPÍTULO IV — DA ATIVIDADE PREVENTIVA",
        "Seção I — Da Divulgação de Informações",
        "Art. 33",
    )


def test_text_of_a_block_containing_nested_blocks_is_kept() -> None:
    # Regression: only innermost blocks were read, so the text of a <p> that
    # also wrapped another block was silently dropped.
    html = "<body><p>Art. 1º Texto do caput<p>§ 1º Parágrafo aninhado.</p></p></body>"
    provisions = {p.id: p for p in StructureParser("x").parse(html_to_lines(html))}
    assert provisions["x:art1"].text == "Texto do caput"
    assert provisions["x:art1:par1"].text == "Parágrafo aninhado."


def test_numbered_annexes() -> None:
    lines = [
        "Art. 1º Aprovar os Anexos I e II.",
        "ANEXO I",
        "REGULAMENTO",
        "Art. 1º Primeiro anexo.",
        "ANEXO II - CLÁUSULAS",
        "Art. 1º Segundo anexo.",
    ]
    provisions = {p.id: p for p in StructureParser("r").parse(lines)}
    assert set(provisions) == {"r:art1", "r:anx1:art1", "r:anx2:art1"}
    assert provisions["r:anx1:art1"].path[0] == "Anexo I — REGULAMENTO"
    assert provisions["r:anx2:art1"].path[0] == "Anexo II — CLÁUSULAS"


def test_orphan_revocation_note_is_not_attached_to_the_previous_provision() -> None:
    # Regression: gov.br strikes Res. 1/2021 annex art. 35, § 4º with its label,
    # leaving "(Revogado pela …)" alone on a line; it was attached to § 3º.
    html = (
        "<body><p>Art. 35. Caput.</p>"
        "<p>§ 3º O agente poderá requerer prorrogação do prazo.</p>"
        "<p><del>§ 4º O não atendimento enseja atuação repressiva.</del> "
        "(Revogado pela Resolução CD/ANPD nº 4, de 24 de fevereiro de 2023)</p>"
        "<p>Art. 36. Seguinte.</p></body>"
    )
    provisions = {p.id: p for p in StructureParser("r").parse(html_to_lines(html))}
    par3 = provisions["r:art35:par3"]
    assert not par3.revoked
    assert par3.amendments == ()
    assert "r:art35:par4" not in provisions


def test_revocation_note_after_a_kept_label_still_revokes() -> None:
    lines = [
        "Art. 7º Caput.",
        "§ 1º",
        "(Revogado pela Lei nº 13.853, de 2019)",
        "§ 2º Em vigor.",
    ]
    provisions = {p.id: p for p in StructureParser("x").parse(lines)}
    assert provisions["x:art7:par1"].revoked
    assert provisions["x:art7:par1"].amendments == ("(Revogado pela Lei nº 13.853, de 2019)",)
    assert not provisions["x:art7:par2"].revoked


def test_rubrics_join_the_path_and_never_the_previous_text() -> None:
    # Regression: gov.br Res. 1/2021 puts unnumbered rubrics before articles;
    # they were appended to the text of the provision above them.
    lines = [
        "CAPÍTULO I",
        "DISPOSIÇÕES GERAIS",
        "Objeto da atuação responsiva",
        "Art. 15. A ANPD adotará atividades de monitoramento.",
        "Parágrafo único. Texto do parágrafo.",
        "Intimação",
        "Art. 16. Primeiro artigo sob a rubrica.",
        "Art. 17. Segundo artigo sob a mesma rubrica.",
        "Seção I",
        "Da Seção",
        "Art. 18. Depois de um novo título.",
    ]
    provisions = {p.id: p for p in StructureParser("r").parse(lines)}
    assert provisions["r:art15:paru"].text == "Texto do parágrafo."
    assert provisions["r:art15"].path == (
        "CAPÍTULO I — DISPOSIÇÕES GERAIS",
        "Objeto da atuação responsiva",
        "Art. 15",
    )
    assert provisions["r:art16"].path[-2:] == ("Intimação", "Art. 16")
    assert provisions["r:art17"].path[-2:] == ("Intimação", "Art. 17")
    assert provisions["r:art18"].path == (
        "CAPÍTULO I — DISPOSIÇÕES GERAIS",
        "Seção I — Da Seção",
        "Art. 18",
    )


def test_a_continuation_line_before_an_article_is_not_a_rubric() -> None:
    lines = ["Art. 1º Caput que continua", "na linha seguinte;", "Art. 2º Outro."]
    provisions = {p.id: p for p in StructureParser("x").parse(lines)}
    assert provisions["x:art1"].text == "Caput que continua na linha seguinte;"
