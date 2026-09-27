from collections.abc import Sequence

import pytest

from base_legal.corpus.ids import ProvisionRef
from base_legal.corpus.models import Provision, ProvisionKind
from base_legal.embeddings.base import Vectors
from base_legal.embeddings.providers import HashingEmbedder
from base_legal.retrieval.fusion import blend, propagate_to_ancestors, reciprocal_rank_fusion
from base_legal.retrieval.refs import candidate_ids, find_references
from base_legal.retrieval.search import Retriever, SearchMode, Tuning
from base_legal.store.db import Ranked


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
        ("O que diz o art. 31 da LAI?", ["lai:art31"]),
        ("art. 31, § 1º, da Lei de Acesso à Informação", ["lai:art31:par1"]),
        ("Lei nº 12.527/2011, art. 4º, IV", ["lai:art4:incIV"]),
        ("art. 23 da lei 12527", ["lai:art23"]),
    ],
)
def test_find_references(question: str, expected: list[str]) -> None:
    assert [str(r) for r in find_references(question)] == expected


def test_references_are_structured() -> None:
    (ref,) = find_references("art. 7º, IX")
    assert ref == ProvisionRef(doc="lgpd", article="7", inciso="IX")


def test_resolution_references_prefer_the_annex_regulation() -> None:
    (ref,) = find_references("art. 6 da Resolução CD/ANPD nº 15/2024")
    assert candidate_ids(ref) == ["res-anpd-15-2024:anx1:art6", "res-anpd-15-2024:art6"]
    (law,) = find_references("art. 6 da LGPD")
    assert candidate_ids(law) == ["lgpd:art6"]


class _Backend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def lexical(self, question: str, limit: int, normalization: int = 0) -> list[Ranked]:
        self.calls.append("lexical")
        return [Ranked("lgpd:art1", 1.0)]

    def dense(self, query_vector: Vectors, limit: int) -> list[Ranked]:
        self.calls.append("dense")
        return [Ranked("lgpd:art2", 0.8)]

    def provisions(self, ids: list[str]) -> dict[str, Provision]:
        return {
            i: Provision(
                id=i,
                document_id="lgpd",
                parent_id=None,
                kind=ProvisionKind.ARTICLE,
                label="Art.",
                text="t",
                path=("Art.",),
                ordinal=0,
            )
            for i in ids
            if i in {"lgpd:art1", "lgpd:art2"}
        }

    def parents(self, ids: list[str]) -> dict[str, str | None]:
        return dict.fromkeys(ids)

    def chunk_contents(self, ids: list[str]) -> dict[str, str]:
        return {i: f"conteúdo de {i}" for i in ids}


@pytest.mark.parametrize(
    ("mode", "calls", "ids", "best"),
    [
        (SearchMode.HYBRID, ["lexical", "dense"], ["lgpd:art1", "lgpd:art2"], 0.8),
        (SearchMode.LEXICAL, ["lexical"], ["lgpd:art1"], None),
        (SearchMode.DENSE, ["dense"], ["lgpd:art2"], 0.8),
    ],
)
def test_search_modes(
    mode: SearchMode, calls: list[str], ids: list[str], best: float | None
) -> None:
    backend = _Backend()
    embedder = None if mode is SearchMode.LEXICAL else HashingEmbedder()
    result = Retriever(backend, embedder, mode=mode).search("pergunta")
    assert backend.calls == calls
    assert [h.provision.id for h in result.hits] == ids
    assert result.best_similarity == best


def test_dense_modes_need_an_embedder() -> None:
    with pytest.raises(ValueError, match="needs a query embedder"):
        Retriever(_Backend(), None, mode=SearchMode.HYBRID)


def test_weighted_rrf() -> None:
    fused = dict(reciprocal_rank_fusion([["a", "b"], ["b", "a"]], k=1, weights=[2.0, 1.0]))
    assert fused["a"] == pytest.approx(2 / 2 + 1 / 3)
    assert fused["b"] == pytest.approx(2 / 3 + 1 / 2)
    with pytest.raises(ValueError, match="one weight per ranking"):
        reciprocal_rank_fusion([["a"]], weights=[1.0, 2.0])


def test_propagate_to_ancestors_lifts_the_article_of_many_matching_incisos() -> None:
    parent_of = {
        "art7:incI": "art7",
        "art7:incII": "art7",
        "art7:incIII": "art7",
        "art7": None,
        "art11:incII:alig": "art11:incII",
        "art11:incII": "art11",
        "art11": None,
    }
    ranked = [
        ("art7:incI", 1.0),
        ("art7:incII", 0.9),
        ("art11:incII:alig", 0.85),
        ("art7:incIII", 0.8),
    ]
    out = propagate_to_ancestors(ranked, parent_of, 0.5)
    scores = dict(out)
    assert out[0][0] == "art7"  # absent before, now first: 0.5 * (1.0 + 0.9 + 0.8)
    assert scores["art7"] == pytest.approx(1.35)
    assert scores["art11:incII"] == pytest.approx(0.425)
    assert scores["art11"] == pytest.approx(0.2125)  # two levels up: weight ** 2
    assert propagate_to_ancestors(ranked, parent_of, 0.0) == ranked


def test_blend_fuses_two_orders_and_keeps_the_first_on_ties() -> None:
    # a and c tie (1/61 + 1/63) above b (2/62); the tie keeps the first-stage order
    assert [pid for pid, _ in blend(["a", "b", "c"], ["c", "b", "a"])] == ["a", "c", "b"]
    assert [pid for pid, _ in blend(["a", "b", "c"], ["c", "a", "b"])] == ["a", "c", "b"]
    [(only, score)] = blend(["a", "b"], ["b"])  # items the reranker did not score are left out
    assert only == "b"
    assert score == pytest.approx(1 / 62 + 1 / 61)


class _Reverse:
    """A fake cross-encoder that prefers the provision ranked last."""

    def __init__(self) -> None:
        self.seen: list[list[str]] = []

    def score(self, question: str, documents: Sequence[str]) -> list[float]:
        self.seen.append(list(documents))
        return [float(n) for n in range(len(documents))]


class _Many(_Backend):
    def lexical(self, question: str, limit: int, normalization: int = 0) -> list[Ranked]:
        return [Ranked(f"lgpd:art{n}", 1.0 / n) for n in range(1, 6)]

    def dense(self, query_vector: Vectors, limit: int) -> list[Ranked]:
        return [Ranked(f"lgpd:art{n}", 1.0 / n) for n in range(1, 6)]

    def provisions(self, ids: list[str]) -> dict[str, Provision]:
        return {
            i: Provision(
                id=i,
                document_id="lgpd",
                parent_id=None,
                kind=ProvisionKind.ARTICLE,
                label="Art.",
                text="t",
                path=("Art.",),
                ordinal=0,
            )
            for i in ids
        }


def test_reranker_reorders_the_head_and_keeps_explicit_references_first() -> None:
    reranker = _Reverse()
    retriever = Retriever(
        _Many(),
        HashingEmbedder(),
        tuning=Tuning(parent_weight=0),
        reranker=reranker,
        rerank_depth=3,
    )
    plain = [
        h.provision.id
        for h in Retriever(_Many(), HashingEmbedder(), tuning=Tuning(parent_weight=0))
        .search("q", k=5)
        .hits
    ]
    assert plain == ["lgpd:art1", "lgpd:art2", "lgpd:art3", "lgpd:art4", "lgpd:art5"]
    result = retriever.search("q", k=5)
    ids = [h.provision.id for h in result.hits]
    # head (art1-3) blended with the reversed order: art2 wins the tie-free blend
    assert set(ids[:3]) == {"lgpd:art1", "lgpd:art2", "lgpd:art3"}
    assert ids[3:] == ["lgpd:art4", "lgpd:art5"]
    assert reranker.seen == [
        ["conteúdo de lgpd:art1", "conteúdo de lgpd:art2", "conteúdo de lgpd:art3"]
    ]
    scores = [h.score for h in result.hits]
    assert scores == sorted(scores, reverse=True)

    explicit = retriever.search("O que diz o art. 5º?", k=5)
    assert explicit.hits[0].provision.id == "lgpd:art5"
    assert explicit.hits[0].explicit
