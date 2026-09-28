"""Local cross-encoder reranking (ADR 0015).

The question and each candidate provision are scored together by a small
multilingual cross-encoder that runs in-process from pinned, hash-verified
weights (safetensors, no remote code), so questions never leave the machine
(ADR 0003). Heavy dependencies are imported lazily (``local`` extra).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

MAX_TOKENS = 512


class Reranker(Protocol):
    def score(self, question: str, documents: Sequence[str]) -> list[float]: ...


class CrossEncoderReranker:
    """A sequence-classification cross-encoder: higher score, more relevant."""

    def __init__(self, path: Path) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        from transformers.utils import logging as hf_logging

        hf_logging.disable_progress_bar()  # keep CLI output and server logs clean
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            path, local_files_only=True
        ).eval()

    def score(self, question: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        batch = self._tokenizer(
            [question] * len(documents),
            list(documents),
            padding=True,
            truncation=True,
            max_length=MAX_TOKENS,
            return_tensors="pt",
        )
        with self._torch.inference_mode():
            logits = self._model(**batch).logits
        return [float(v) for v in logits[:, 0]]
