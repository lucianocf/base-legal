"""The in-repo voyage-4-nano encoder reproduces the vendor's remote code (ADR 0012).

Needs the ``local`` extra and the pinned weights (``base-legal model fetch``);
skipped otherwise. The evals workflow exercises the encoder end to end.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from base_legal.config import Settings
from base_legal.embeddings.factory import make_query_embedder

pytest.importorskip("torch")
pytest.importorskip("transformers")

MODELS = Path(__file__).parents[2] / "models"
REFERENCE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "nano_reference.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def nano():  # type: ignore[no-untyped-def]  # the embedder (optional extra)
    if not (MODELS / "voyage-4-nano" / "model.safetensors").is_file():
        pytest.skip("voyage-4-nano weights not fetched")
    return make_query_embedder(Settings(models_dir=MODELS))


def test_matches_the_vendor_remote_code(nano) -> None:  # type: ignore[no-untyped-def]
    texts = REFERENCE["texts"]
    queries = np.stack([nano.embed_query(t) for t in texts])[:, :64]
    documents = nano.embed_documents(texts)[:, :64]  # batched with padding
    np.testing.assert_allclose(queries, np.array(REFERENCE["queries"]), atol=1e-5)
    np.testing.assert_allclose(documents, np.array(REFERENCE["documents"]), atol=1e-5)


def test_shape_normalization_and_no_remote_code(nano) -> None:  # type: ignore[no-untyped-def]
    vectors = nano.embed_documents(["um", "dois textos", ""])
    assert vectors.shape == (3, 1024)
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)
    assert nano.embed_documents([]).shape == (0, 1024)
    assert type(nano).__module__ == "base_legal.embeddings.nano"
    assert not hasattr(nano, "_backend")  # no sentence-transformers / remote code path
