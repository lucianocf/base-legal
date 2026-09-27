"""Hybrid retrieval: explicit references, then FTS + vector fused with RRF (ADR 0004)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from base_legal.corpus.models import Provision
from base_legal.embeddings.base import Embedder, Vectors
from base_legal.retrieval.fusion import reciprocal_rank_fusion
from base_legal.retrieval.refs import candidate_ids, find_references
from base_legal.store.db import Ranked


class SearchBackend(Protocol):
    def lexical(self, question: str, limit: int) -> list[Ranked]: ...

    def dense(self, query_vector: Vectors, limit: int) -> list[Ranked]: ...

    def provisions(self, ids: list[str]) -> dict[str, Provision]: ...


@dataclass(frozen=True, slots=True)
class Hit:
    provision: Provision
    score: float
    explicit: bool = False


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: tuple[Hit, ...]
    best_similarity: float | None
    missing_references: tuple[str, ...] = field(default=())


class Retriever:
    def __init__(
        self, backend: SearchBackend, embedder: Embedder, *, candidate_pool: int = 50
    ) -> None:
        self.backend = backend
        self.embedder = embedder
        self.candidate_pool = candidate_pool

    def search(self, question: str, k: int = 8) -> SearchResult:
        """``question`` must already be redacted by :mod:`base_legal.privacy`."""
        candidates = [candidate_ids(r) for r in find_references(question)]
        found = self.backend.provisions([c for group in candidates for c in group])
        explicit: list[str] = []
        missing: list[str] = []
        for group in candidates:
            match = next((c for c in group if c in found), None)
            if match is None:
                missing.append(group[-1])
            elif found[match].is_normative and match not in explicit:
                explicit.append(match)

        lexical = self.backend.lexical(question, self.candidate_pool)
        dense = self.backend.dense(self.embedder.embed_query(question), self.candidate_pool)
        fused = reciprocal_rank_fusion(
            [[r.provision_id for r in lexical], [r.provision_id for r in dense]]
        )

        ranked: list[tuple[str, float, bool]] = [(ref, 1.0, True) for ref in explicit]
        seen = set(explicit)
        for provision_id, score in fused:
            if provision_id not in seen:
                ranked.append((provision_id, score, False))
                seen.add(provision_id)
        ranked = ranked[:k]

        provisions = self.backend.provisions([pid for pid, _, _ in ranked])
        hits = tuple(
            Hit(provisions[pid], score, is_explicit)
            for pid, score, is_explicit in ranked
            if pid in provisions
        )
        best = max((r.score for r in dense), default=None)
        return SearchResult(hits=hits, best_similarity=best, missing_references=tuple(missing))
