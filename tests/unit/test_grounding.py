import pytest

from base_legal.corpus.models import Provision, ProvisionKind
from base_legal.grounding.validator import (
    AnswerBlock,
    Citation,
    CitationIssue,
    check_citation,
    judge,
    normalize_for_match,
)


def _provision(pid: str, text: str, *, revoked: bool = False) -> Provision:
    return Provision(
        id=pid,
        document_id="lgpd",
        parent_id=None,
        kind=ProvisionKind.ARTICLE,
        label="Art.",
        text=text,
        path=("Art.",),
        revoked=revoked,
        ordinal=0,
    )


CORPUS = {
    "lgpd:art7:incIX": _provision(
        "lgpd:art7:incIX",
        "quando necessário para atender aos interesses legítimos do controlador ou de terceiro;",
    ),
    "lgpd:art7:par1": _provision("lgpd:art7:par1", "", revoked=True),
    "lgpd:art28": Provision(
        id="lgpd:art28",
        document_id="lgpd",
        parent_id=None,
        kind=ProvisionKind.ARTICLE,
        label="Art. 28",
        text="",
        path=("Art. 28",),
        vetoed=True,
        ordinal=1,
    ),
    "lgpd:art1": _provision(
        "lgpd:art1", "Esta Lei dispõe sobre o tratamento de dados — “pessoais”."
    ),
}


def test_valid_citation() -> None:
    citation = Citation("lgpd:art7:incIX", "atender aos interesses legítimos do controlador")
    assert check_citation(citation, CORPUS) is None


@pytest.mark.parametrize(
    ("citation", "issue"),
    [
        (Citation("lgpd:art7:inc9", "qualquer coisa aqui"), CitationIssue.MALFORMED_ID),
        (Citation("lgpd:art7:incXII", "autoriza a venda de dados"), CitationIssue.UNKNOWN_ID),
        (Citation("lgpd:art7:par1", "texto revogado qualquer"), CitationIssue.REVOKED),
        (Citation("lgpd:art28", "texto vetado qualquer"), CitationIssue.VETOED),
        (Citation("lgpd:art7:incIX", "legítimos"), CitationIssue.QUOTE_TOO_SHORT),
        (
            Citation("lgpd:art7:incIX", "interesses legítimos do titular"),
            CitationIssue.QUOTE_NOT_FOUND,
        ),
    ],
)
def test_invalid_citations(citation: Citation, issue: CitationIssue) -> None:
    assert check_citation(citation, CORPUS) is issue


def test_typographic_normalization() -> None:
    quote = 'tratamento de dados - "pessoais"'
    assert check_citation(Citation("lgpd:art1", quote), CORPUS) is None
    assert normalize_for_match("a\xa0 b – c") == "a b - c"


def test_judge_accepts_fully_cited_answer() -> None:
    blocks = [
        AnswerBlock("Sim, é possível. "),
        AnswerBlock(
            "O legítimo interesse do controlador é uma das hipóteses legais de tratamento.",
            (Citation("lgpd:art7:incIX", "interesses legítimos do controlador ou de terceiro"),),
        ),
    ]
    verdict = judge(blocks, CORPUS)
    assert verdict.grounded
    assert verdict.reasons == ()


def test_judge_rejects_uncited_substantive_block() -> None:
    blocks = [
        AnswerBlock(
            "O legítimo interesse é hipótese legal.",
            (Citation("lgpd:art7:incIX", "interesses legítimos do controlador"),),
        ),
        AnswerBlock("Além disso, a venda de dados de clientes é sempre permitida sem aviso."),
    ]
    verdict = judge(blocks, CORPUS)
    assert not verdict.grounded
    assert verdict.uncited_blocks == (1,)


def test_judge_rejects_invalid_citation_even_if_others_are_valid() -> None:
    blocks = [
        AnswerBlock(
            "A lei autoriza a venda de dados pessoais de clientes.",
            (
                Citation("lgpd:art7:incIX", "interesses legítimos do controlador"),
                Citation("lgpd:art7:incXII", "autoriza a venda de dados"),
            ),
        )
    ]
    verdict = judge(blocks, CORPUS)
    assert not verdict.grounded
    assert verdict.invalid[0][1] is CitationIssue.UNKNOWN_ID


def test_judge_rejects_answer_without_citations() -> None:
    verdict = judge([AnswerBlock("Não sei.")], CORPUS)
    assert not verdict.grounded
    assert "no valid citation" in verdict.reasons
