"""The in-repo cross-encoder matches sentence-transformers' CrossEncoder (ADR 0015).

Needs the ``local`` extra and the pinned weights (``base-legal model fetch``);
skipped otherwise.
"""

import json
from pathlib import Path

import pytest

from base_legal.config import Settings
from base_legal.embeddings.factory import make_reranker

pytest.importorskip("torch")
pytest.importorskip("transformers")

MODELS = Path(__file__).parents[2] / "models"
REFERENCE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "reranker_reference.json").read_text("utf-8")
)


def test_matches_the_reference_cross_encoder() -> None:
    if not (MODELS / "mmarco-mminilmv2" / "model.safetensors").is_file():
        pytest.skip("reranker weights not fetched")
    reranker = make_reranker(Settings(models_dir=MODELS, reranker="mmarco-mminilmv2"))
    assert reranker is not None
    for (question, document), expected in zip(REFERENCE["pairs"], REFERENCE["logits"], strict=True):
        assert reranker.score(question, [document]) == pytest.approx([expected], abs=1e-3)
    # batched with padding, same scores
    questions = {q for q, _ in REFERENCE["pairs"]}
    for question in questions:
        docs = [d for q, d in REFERENCE["pairs"] if q == question]
        want = [
            e
            for (q, _), e in zip(REFERENCE["pairs"], REFERENCE["logits"], strict=True)
            if q == question
        ]
        assert reranker.score(question, docs) == pytest.approx(want, abs=1e-3)


def test_no_reranker_when_disabled() -> None:
    assert make_reranker(Settings(reranker="none")) is None
    assert Settings(reranker="").reranker is None
