import pytest

from base_legal.corpus.xrefs import (
    Candidate,
    CrossReference,
    find_candidates,
    regulation_index,
    resolve,
)

REGULATIONS = regulation_index(
    [
        ("res-anpd-4-2023", "1", "Anexo — REGULAMENTO DE DOSIMETRIA E APLICAÇÃO DE SANÇÕES"),
        ("res-anpd-15-2024", "1", "Anexo — REGULAMENTO DE COMUNICAÇÃO DE INCIDENTE DE SEGURANÇA"),
        ("lgpd", "1", "Anexo — Tabela sem regulamento"),  # not a regulation: ignored
    ]
)


def links(provision_id: str, text: str) -> list[tuple[str, tuple[str, ...]]]:
    return [
        (text[c.start : c.end], c.targets) for c in find_candidates(provision_id, text, REGULATIONS)
    ]


@pytest.mark.parametrize(
    ("provision_id", "text", "expected"),
    [
        # smallest unit first, qualified by the act itself
        (
            "lgpd:art52:par1",
            "nos termos do inciso II do § 2º do art. 48 desta Lei.",
            [("inciso II do § 2º do art. 48 desta Lei", ("lgpd:art48:par2:incII",))],
        ),
        # forward order
        (
            "res-anpd-2-2022:anx1:art11",
            "o disposto no art. 52, § 1º, inciso IX, da LGPD",
            [("art. 52, § 1º, inciso IX, da LGPD", ("lgpd:art52:par1:incIX",))],
        ),
        # "caput deste artigo" from a paragraph is the article itself
        (
            "lgpd:art38:paru",
            "O disposto no caput deste artigo aplica-se",
            [("caput deste artigo", ("lgpd:art38",))],
        ),
        # "inciso V do caput deste artigo"
        (
            "lgpd:art11:par1",
            "o inciso V do caput deste artigo não inclui",
            [("inciso V do caput deste artigo", ("lgpd:art11:incV",))],
        ),
        # a bare paragraph borrows the article
        (
            "lgpd:art14:par5",
            "as informações de que trata o § 1º deste artigo",
            [("§ 1º deste artigo", ("lgpd:art14:par1",))],
        ),
        # a bare inciso inside a paragraph: the paragraph's own, else the caput's
        (
            "lgpd:art52:par3",
            "o disposto no inciso VI",
            [("inciso VI", ("lgpd:art52:par3:incVI", "lgpd:art52:incVI"))],
        ),
        # a bare alínea inside an alínea: a sibling under the same inciso
        (
            "res-anpd-19-2024:anx1:art8:par1:incII:alic",
            'observado o disposto na alínea "a"',
            [('alínea "a"', ("res-anpd-19-2024:anx1:art8:par1:incII:alia",))],
        ),
        # plural lists: one link per item; ranges link their endpoints
        (
            "lgpd:art4:incII",
            "nos arts. 7º e 11 desta Lei",
            [("arts. 7º", ("lgpd:art7",)), ("11 desta Lei", ("lgpd:art11",))],
        ),
        (
            "res-anpd-4-2023:anx1:art3:par5",
            "incisos I e IV a IX, do caput deste artigo",
            [
                ("incisos I", ("res-anpd-4-2023:anx1:art3:incI",)),
                ("IV", ("res-anpd-4-2023:anx1:art3:incIV",)),
                ("IX, do caput deste artigo", ("res-anpd-4-2023:anx1:art3:incIX",)),
            ],
        ),
        # a regulation cited by name resolves to that resolution's annex
        (
            "res-anpd-15-2024:anx1:art2",
            "conforme o art. 9º do Regulamento de Dosimetria e Aplicação de Sanções",
            [
                (
                    "art. 9º do Regulamento de Dosimetria e Aplicação de Sanções",
                    ("res-anpd-4-2023:anx1:art9",),
                )
            ],
        ),
        # "deste Regulamento": the annex of the citing resolution
        (
            "res-anpd-15-2024:anx1:art16:par2",
            "no art. 5º deste Regulamento",
            [("art. 5º deste Regulamento", ("res-anpd-15-2024:anx1:art5",))],
        ),
        # "do Anexo da Resolução …"
        (
            "res-anpd-19-2024:anx1:art34",
            "o disposto no art. 12 do Anexo da Resolução CD/ANPD nº 1, de 28 de outubro de 2021,",
            [
                (
                    "art. 12 do Anexo da Resolução CD/ANPD nº 1, de 28 de outubro de 2021",
                    ("res-anpd-1-2021:anx1:art12",),
                )
            ],
        ),
        # a resolution cited by number: its annex regulation first, then the resolution
        (
            "lgpd:art1",
            "art. 3º da Resolução CD/ANPD nº 2, de 27 de janeiro de 2022",
            [
                (
                    "art. 3º da Resolução CD/ANPD nº 2, de 27 de janeiro de 2022",
                    ("res-anpd-2-2022:art3", "res-anpd-2-2022:anx1:art3"),
                )
            ],
        ),
        # "art. 6º., §5º." (ordinal followed by a period, no space after §)
        (
            "res-anpd-15-2024:anx1:art18",
            "na forma do art. 6º., §5º.",
            [("art. 6º., §5º.", ("res-anpd-15-2024:anx1:art6:par5",))],
        ),
    ],
)
def test_reference_phrases(
    provision_id: str, text: str, expected: list[tuple[str, tuple[str, ...]]]
) -> None:
    assert links(provision_id, text) == expected


def test_a_qualifier_at_the_end_of_an_enumeration_applies_to_every_item() -> None:
    text = (
        "nos termos do art. 33, incisos I e II, alíneas 'a', 'b' e 'c', art. 34, art. 35, "
        "caput e §§ 1º, 2º e 5º, e art. 36 da Lei nº 13.709, de 14 de agosto de 2018."
    )
    assert [targets for _, targets in links("res-anpd-19-2024:art1", text)] == [
        # "art. 33, incisos I e II, alíneas a, b e c": two lists, too ambiguous
        ("lgpd:art34",),
        ("lgpd:art35",),
        ("lgpd:art35:par1",),  # items without an article take the previous one's
        ("lgpd:art35:par2",),
        ("lgpd:art35:par5",),
        ("lgpd:art36",),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "sujeitas ao disposto no art. 173 da Constituição Federal",
        "nos termos do art. 41 da Lei nº 14.195, de 26 de agosto de 2021",
        "o art. 966 da Lei nº 10.406, de 10 de janeiro de 2002 (Código Civil)",
        "o art. 26, inciso IV do Anexo I do Decreto nº 10.474, de 2020",
        "com base no art. 55-J, inciso XVIII, da referida Lei.",
        # the act is named after a filler, past a second phrase
        "previsto nos incisos I e II do art. 3º ou no § 1º do art. 18-A, conforme o caso, "
        "da Lei Complementar nº 123, de 14 de dezembro de 2006",
    ],
)
def test_references_to_acts_outside_the_corpus_are_not_linked(text: str) -> None:
    assert links("res-anpd-2-2022:anx1:art2:incII", text) == []


def test_quoted_amendment_text_is_not_linked() -> None:
    text = (
        "O inciso II do art. 14 do Regulamento de Dosimetria e Aplicação de Sanções passa a "
        'vigorar com a seguinte redação: "Art. 14. (...) II - no caso do § 1º do art. 6º"'
    )
    assert links("res-anpd-15-2024:art2", text) == [
        (
            "inciso II do art. 14 do Regulamento de Dosimetria e Aplicação de Sanções",
            ("res-anpd-4-2023:anx1:art14:incII",),
        )
    ]


def test_the_law_by_name_and_by_number() -> None:
    assert links("res-anpd-4-2023:anx1:art27", "do art. 52 da Lei Geral de Proteção de Dados") == [
        ("art. 52 da Lei Geral de Proteção de Dados", ("lgpd:art52",))
    ]
    assert links("res-anpd-2-2022:anx1:art2", "o parágrafo único do art. 1º da Lei nº 12.527") == [
        ("parágrafo único do art. 1º da Lei nº 12.527", ("lai:art1:paru",))
    ]


def test_an_unknown_regulation_name_is_not_linked() -> None:
    assert links("lgpd:art1", "o art. 2º do Regulamento Interno da Casa") == []


def test_resolve_keeps_the_first_existing_candidate_and_never_self_links() -> None:
    candidates = [
        Candidate(0, 5, ("lgpd:art52:par3:incVI", "lgpd:art52:incVI")),
        Candidate(10, 15, ("lgpd:art99",)),
        Candidate(20, 25, ("lgpd:art7",)),
    ]
    existing = {"lgpd:art52:incVI", "lgpd:art7"}
    assert resolve("lgpd:art8", candidates, existing) == (
        CrossReference(0, 5, "lgpd:art52:incVI"),
        CrossReference(20, 25, "lgpd:art7"),
    )
    assert resolve("lgpd:art7", candidates[2:], existing) == ()


def test_text_without_references() -> None:
    assert (
        find_candidates("lgpd:art1", "Esta Lei dispõe sobre o tratamento de dados pessoais.") == []
    )
