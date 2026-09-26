import pytest

from base_legal.corpus.ids import ProvisionRef
from base_legal.retrieval.fusion import reciprocal_rank_fusion
from base_legal.retrieval.refs import find_references


def test_rrf_rewards_agreement() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]], k=60)
    assert [item for item, _ in fused] == ["a", "b", "c", "d"]
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)


def test_rrf_ignores_duplicates_within_a_ranking() -> None:
    fused = dict(reciprocal_rank_fusion([["a", "a", "b"]]))
    assert fused["a"] == pytest.approx(1 / 61)
    assert fused["b"] == pytest.approx(1 / 63)


def test_rrf_rejects_bad_k() -> None:
    with pytest.raises(ValueError, match="positive"):
        reciprocal_rank_fusion([["a"]], k=0)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("O que diz o art. 7º, inciso IX, da LGPD?", ["lgpd:art7:incIX"]),
        ("artigo 7, IX", ["lgpd:art7:incIX"]),
        ("Art. 48, § 1º, III", ["lgpd:art48:par1:incIII"]),
        ("art. 11, II, alínea g", ["lgpd:art11:incII:alig"]),
        ('art. 11, II, "g"', ["lgpd:art11:incII:alig"]),
        ("art. 24, parágrafo único", ["lgpd:art24:paru"]),
        ("art. 55-J, IV", ["lgpd:art55J:incIV"]),
        ("art. 65, I-A", ["lgpd:art65:incI-A"]),
        ("O que diz o art. 99 da LGPD?", ["lgpd:art99"]),
        ("Compare o art. 7º e o art. 11", ["lgpd:art7", "lgpd:art11"]),
        ("art. 7º, IX e X", ["lgpd:art7:incIX"]),
        ("art. 6 da Resolução CD/ANPD nº 15/2024", ["res-anpd-15-2024:art6"]),
        (
            "Resolução CD/ANPD nº 18, de 16 de julho de 2024, art. 3",
            ["res-anpd-18-2024:art3"],
        ),
        ("Quais são os direitos do titular?", []),
    ],
)
def test_find_references(question: str, expected: list[str]) -> None:
    assert [str(r) for r in find_references(question)] == expected


def test_references_are_structured() -> None:
    (ref,) = find_references("art. 7º, IX")
    assert ref == ProvisionRef(doc="lgpd", article="7", inciso="IX")
