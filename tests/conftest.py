from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(autouse=True)
def _no_reranker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests run without the reranker's weights (fetched only by `model fetch`);
    tests of the reranker itself load it explicitly."""
    monkeypatch.setenv("BASE_LEGAL_RERANKER", "none")
