from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_image_ships_the_corpus_files_ingest_reads() -> None:
    # Regression: the image copied the parsed documents but not
    # corpus/history/, so `ingest` in Docker stored no earlier wordings and
    # /provisions/{id}/history was empty (ADR 0014).
    sources = {
        source
        for line in (ROOT / "Dockerfile").read_text("utf-8").splitlines()
        if line.startswith("COPY corpus/")
        for source in line.split()[1:-1]
    }
    assert {"corpus/manifest.yaml", "corpus/*.json", "corpus/history"} <= sources
    assert any((ROOT / "corpus" / "history").glob("*.json"))
