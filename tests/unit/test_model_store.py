import hashlib
from pathlib import Path

import httpx
import pytest

from base_legal.embeddings.model_store import (
    ModelIntegrityError,
    ModelLock,
    fetch_model,
    load_lock,
    verify_model,
)

FILES = {"config.json": b"{}", "code.py": b"print('reviewed')\n"}


def _lock() -> ModelLock:
    return ModelLock(
        repo="org/model",
        revision="a" * 40,
        license="apache-2.0",
        files={name: hashlib.sha256(body).hexdigest() for name, body in FILES.items()},
    )


def _client(files: dict[str, bytes]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert f"/resolve/{'a' * 40}/" in request.url.path
        return httpx.Response(200, content=files[request.url.path.rsplit("/", 1)[1]])

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_and_verify(tmp_path: Path) -> None:
    assert sorted(fetch_model(_lock(), tmp_path, _client(FILES))) == ["code.py", "config.json"]
    assert fetch_model(_lock(), tmp_path, _client(FILES)) == []  # idempotent
    verify_model(_lock(), tmp_path)


def test_tampered_download_is_rejected(tmp_path: Path) -> None:
    evil = {**FILES, "code.py": b"import os; os.system('curl evil')\n"}
    with pytest.raises(ModelIntegrityError, match="does not match"):
        fetch_model(_lock(), tmp_path, _client(evil))
    assert not (tmp_path / "code.py").exists()


def test_tampered_file_on_disk_and_unreviewed_code(tmp_path: Path) -> None:
    fetch_model(_lock(), tmp_path, _client(FILES))
    (tmp_path / "code.py").write_bytes(b"changed")
    with pytest.raises(ModelIntegrityError, match=r"hash mismatch code\.py"):
        verify_model(_lock(), tmp_path)
    fetch_model(_lock(), tmp_path, _client(FILES))
    (tmp_path / "extra.py").write_text("x = 1")
    with pytest.raises(ModelIntegrityError, match=r"unreviewed code file extra\.py"):
        verify_model(_lock(), tmp_path)


def test_shipped_nano_lock() -> None:
    lock = load_lock("voyage-4-nano")
    assert lock.license == "apache-2.0"
    assert len(lock.revision) == 40
    # Loaded by base_legal.embeddings.nano; the repo's remote code is never run (ADR 0012).
    assert not lock.trust_remote_code
    assert lock.remote_code is None
    assert lock.note is not None
    assert "ADR 0012" in lock.note
    assert "model.safetensors" in lock.files
