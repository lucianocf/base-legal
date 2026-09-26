"""Pinned, hash-verified local model weights (ADR 0003, threat S12).

A lockfile shipped with the package records the Hugging Face revision and the
SHA-256 of every file, including any remote code, which must have been
reviewed. Weights are downloaded once (``base-legal model fetch``) and every
load re-verifies all hashes, so the code and weights executed are exactly
the reviewed ones.
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

_CHUNK = 1 << 20


class RemoteCode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewed: bool
    files: list[str]
    review_note: str


class ModelLock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo: str
    revision: str
    license: str
    remote_code: RemoteCode | None = None
    files: dict[str, str]

    @property
    def trust_remote_code(self) -> bool:
        return self.remote_code is not None and self.remote_code.reviewed


class ModelIntegrityError(RuntimeError):
    """A model file is missing or does not match the pinned hash."""


def load_lock(name: str = "voyage-4-nano") -> ModelLock:
    text = resources.files("base_legal.embeddings").joinpath(f"{name}.lock.json").read_text()
    return ModelLock.model_validate(json.loads(text))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model(lock: ModelLock, directory: Path) -> None:
    problems: list[str] = []
    for relative, expected in lock.files.items():
        path = directory / relative
        if not path.is_file():
            problems.append(f"missing {relative}")
        elif file_sha256(path) != expected:
            problems.append(f"hash mismatch {relative}")
    unexpected = {
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and p.suffix == ".py"
    } - set(lock.files)
    problems += [f"unreviewed code file {name}" for name in sorted(unexpected)]
    if problems:
        raise ModelIntegrityError(f"{lock.repo}@{lock.revision[:12]}: " + "; ".join(problems))


def fetch_model(lock: ModelLock, directory: Path, client: httpx.Client) -> list[str]:
    """Download missing or mismatching files at the pinned revision; return what was fetched."""
    fetched: list[str] = []
    for relative, expected in lock.files.items():
        path = directory / relative
        if path.is_file() and file_sha256(path) == expected:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        url = f"https://huggingface.co/{lock.repo}/resolve/{lock.revision}/{relative}"
        digest = hashlib.sha256()
        with client.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(_CHUNK):
                    digest.update(chunk)
                    handle.write(chunk)
        if digest.hexdigest() != expected:
            partial.unlink()
            raise ModelIntegrityError(f"downloaded {relative} does not match the pinned hash")
        partial.replace(path)
        fetched.append(relative)
    verify_model(lock, directory)
    return fetched
