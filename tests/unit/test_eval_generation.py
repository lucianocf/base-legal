from pathlib import Path

import pytest
from typer.testing import CliRunner

from base_legal.cli.app import app
from base_legal.evals.generation import citation_recall, covers, evaluate_generation, to_markdown
from base_legal.evals.golden import GoldenSet, Split
from base_legal.generation.answer import (
    Answer,
    AnswerPart,
    CitedQuote,
    RefusalCause,
    Status,
    Usage,
)

GOLDEN = GoldenSet.model_validate(
    {
        "version": 1,
        "answerable": [
            {
                "id": "a1",
                "question": "Pergunta sintética A?",
                "expected": ["lgpd:art18"],
                "split": "dev",
                "status": "unverified",
            },
            {
                "id": "a2",
                "question": "Pergunta sintética B?",
                "expected": ["lgpd:art7:incIX", "lgpd:art10"],
                "split": "dev",
                "status": "unverified",
            },
        ],
        "refuse": [
            {
                "id": "r1",
                "question": "Pergunta fora do corpus?",
                "reason": "out_of_corpus",
                "split": "dev",
                "status": "unverified",
            }
        ],
    }
)


class _Answerer:
    def answer(self, question: str) -> Answer:
        usage = Usage(input_tokens=100, output_tokens=10, cache_read_input_tokens=50)
        if question.endswith("A?"):
            quote = CitedQuote(provision_id="lgpd:art18:incV", quote="portabilidade")
            return Answer(
                status=Status.ANSWERED,
                parts=(AnswerPart(text="Sim.", citations=(quote,)),),
                usage=usage,
            )
        if question.endswith("B?"):
            quote = CitedQuote(provision_id="lgpd:art7:incIX", quote="interesse")
            return Answer(
                status=Status.ANSWERED,
                parts=(AnswerPart(text="Pode.", citations=(quote,)),),
                usage=usage,
            )
        return Answer(status=Status.REFUSED, refusal=RefusalCause.LOW_SCORE)


def test_covers_and_citation_recall() -> None:
    assert covers("lgpd:art18:incV", "lgpd:art18")
    assert covers("lgpd:art18", "lgpd:art18:incV")
    assert not covers("lgpd:art1", "lgpd:art18")  # a prefix of the string is not an ancestor
    assert citation_recall(["lgpd:art7:incIX"], ["lgpd:art7:incIX", "lgpd:art10"]) == 0.5


def test_generation_report_has_metrics_and_no_text() -> None:
    report = evaluate_generation(
        _Answerer(), GOLDEN, split=Split.DEV, model="claude-haiku-4-5", label="t"
    )
    m = report.metrics
    assert m.answered_rate == 1.0
    assert m.citation_recall == pytest.approx(0.75)
    assert m.refusal_accuracy == 1.0
    assert (m.input_tokens, m.output_tokens, m.cache_read_input_tokens) == (200, 20, 100)
    markdown = to_markdown(report)
    assert "Pergunta sintética" not in markdown + report.model_dump_json()
    assert "Sim." not in markdown + report.model_dump_json()
    limited = evaluate_generation(
        _Answerer(), GOLDEN, split=Split.DEV, model="m", label="t", limit=1
    )
    assert [i.id for i in limited.items] == ["a1"]


def test_cli_requires_explicit_confirmation(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["eval", "generation", "--out-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert "--yes" in result.output
