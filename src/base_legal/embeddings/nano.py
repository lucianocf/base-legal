"""voyage-4-nano without remote code (ADR 0012).

The model is Qwen3 with bidirectional attention and a linear head
(hidden 1024 -> 2048), mean-pooled and normalized; the first 1024 dimensions
are used (Matryoshka). Its Hugging Face repository ships that architecture as
remote code written for transformers 4.x; transformers 4.x has published
vulnerabilities fixed only in 5.x, where the remote code no longer loads.

This module rebuilds the same computation on transformers' own ``Qwen3Model``,
so nothing from the model repository is ever executed: only the pinned,
hash-verified weights, tokenizer and configuration are read. The embeddings
match the vendor code to within float32 rounding (max abs diff 1.5e-8,
checked 2026-09-27; ``tests/integration/test_nano.py``).

Heavy dependencies (torch, transformers) are imported lazily: they come with
the optional ``local`` extra.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from base_legal.embeddings.base import EMBEDDING_DIM, Vectors, l2_normalize, model_family

BATCH_SIZE = 16
MAX_TOKENS = 8192  # far above any provision; bounds memory on hostile input


def _encoder_class() -> Any:  # Any: a torch module class built on first use
    import torch
    from torch import nn
    from transformers import PreTrainedModel, Qwen3Config, Qwen3Model

    class NanoEncoder(PreTrainedModel):  # type: ignore[misc]  # untyped base class
        """Qwen3 with bidirectional attention and the model's linear head."""

        config_class = Qwen3Config
        base_model_prefix = ""
        _supports_sdpa = True

        def __init__(self, config: Any) -> None:
            super().__init__(config)
            self.model = Qwen3Model(config)
            self.linear = nn.Linear(config.hidden_size, config.num_labels, bias=False)
            self.post_init()
            for layer in self.model.layers:
                layer.self_attn.is_causal = False

        def forward(self, input_ids: Any, attention_mask: Any) -> Any:
            embeds = self.model.embed_tokens(input_ids)
            length = input_ids.shape[1]
            # Every token attends to every non-padding token (no causal mask).
            keep = attention_mask[:, None, None, :].to(torch.bool).expand(-1, 1, length, -1)
            additive = torch.zeros(keep.shape, dtype=embeds.dtype, device=embeds.device)
            additive = additive.masked_fill(~keep, torch.finfo(embeds.dtype).min)
            out = self.model(
                inputs_embeds=embeds, attention_mask={"full_attention": additive}, use_cache=False
            )
            return self.linear(out.last_hidden_state)

    return NanoEncoder


class NanoEmbedder:
    """Local, in-process voyage-4-nano. Loads only from a verified directory."""

    def __init__(self, path: Path, model: str = "voyage-4-nano") -> None:
        import torch
        from transformers import AutoTokenizer

        self._torch = torch
        self._model_name = model
        prompts = json.loads((path / "config_sentence_transformers.json").read_text("utf-8"))
        self._prompts: dict[str, str] = prompts["prompts"]
        self._tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self._encoder = (
            _encoder_class()
            .from_pretrained(path, local_files_only=True, dtype=torch.float32)
            .eval()
        )

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def family(self) -> str:
        return model_family(self._model_name)

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def _encode(self, texts: Sequence[str], kind: str) -> Vectors:
        torch = self._torch
        prompt = self._prompts[kind]
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))  # less padding
        out = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
        for start in range(0, len(order), BATCH_SIZE):
            index = order[start : start + BATCH_SIZE]
            batch = self._tokenizer(
                [prompt + texts[i] for i in index],
                padding=True,
                truncation=True,
                max_length=MAX_TOKENS,
                return_tensors="pt",
            )
            with torch.inference_mode():
                hidden = self._encoder(batch["input_ids"], batch["attention_mask"])
            mask = batch["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1)
            out[index] = pooled[:, :EMBEDDING_DIM].float().numpy()
        return l2_normalize(out)

    def embed_documents(self, texts: Sequence[str]) -> Vectors:
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        return self._encode(texts, "document")

    def embed_query(self, text: str) -> Vectors:
        return np.asarray(self._encode([text], "query")[0], dtype=np.float32)
