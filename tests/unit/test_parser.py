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
