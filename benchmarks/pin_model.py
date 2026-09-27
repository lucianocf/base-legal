"""Pin a benchmark-only embedding model: revision + SHA-256 of every file (ADR 0003).

Benchmark models (plan B candidates for the embedding gate) are never
production dependencies. Their locks live here, not in the package. Each
file is downloaded at a fixed commit and hashed; files stored with Git LFS
must match the SHA-256 Hugging Face records for them. Only safetensors
weights are allowed.

    uv run python benchmarks/pin_model.py Qwen/Qwen3-Embedding-0.6B <commit> \\
        --license apache-2.0 --out benchmarks/models/qwen3-embedding-0.6b.lock.json \\
        config.json model.safetensors ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import httpx

API = "https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=1"
RESOLVE = "https://huggingface.co/{repo}/resolve/{revision}/{path}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("revision", help="full commit hash")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--license", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    if len(args.revision) != 40:
        parser.error("revision must be a full 40-character commit hash")
    if any(f.endswith((".bin", ".pt", ".pth", ".pkl", ".ckpt")) for f in args.files):
        parser.error("pickle-based weights are not allowed; pin safetensors only")
    if any(f.endswith(".py") for f in args.files):
        parser.error("remote code needs a manual review; not supported by this script")

    with httpx.Client(timeout=httpx.Timeout(60, read=600), follow_redirects=True) as client:
        tree = client.get(API.format(repo=args.repo, revision=args.revision)).raise_for_status()
        lfs = {f["path"]: f["lfs"]["oid"] for f in tree.json() if f.get("lfs")}
        hashes: dict[str, str] = {}
        for path in args.files:
            digest = hashlib.sha256()
            url = RESOLVE.format(repo=args.repo, revision=args.revision, path=path)
            with client.stream("GET", url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(1 << 20):
                    digest.update(chunk)
            hashes[path] = digest.hexdigest()
            if path in lfs and lfs[path] != hashes[path]:
                raise SystemExit(f"{path}: SHA-256 differs from the LFS pointer")
            print(f"{path}: {hashes[path]}{' (matches LFS)' if path in lfs else ''}")

    lock = {
        "repo": args.repo,
        "revision": args.revision,
        "license": args.license,
        "remote_code": None,
        "files": dict(sorted(hashes.items())),
    }
    if args.note:
        lock["note"] = args.note
    args.out.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
