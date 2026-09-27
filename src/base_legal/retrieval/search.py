"""Hybrid retrieval: explicit references, then FTS + vector fused with RRF (ADR 0004)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from base_legal.corpus.models import Provision
from base_legal.embeddings.base import Embedder, Vectors
from base_legal.retrieval.fusion import propagate_to_ancestors, reciprocal_rank_fusion
from base_legal.retrieval.refs import candidate_ids, find_references
from base_legal.store.db import Ranked


class SearchBackend(Protocol):
    def lexical(self, question: str, limit: int, normalization: int = 0) -> list[Ranked]: ...

    def dense(self, query_vector: Vectors, limit: int) -> list[Ranked]: ...

    def provisions(self, ids: list[str]) -> dict[str, Provision]: ...

    def parents(self, ids: list[str]) -> dict[str, str | None]: ...


@dataclass(frozen=True, slots=True)
class Tuning:
    """Retrieval knobs (tuned on the golden dev split, confirmed on holdout)."""

    fts_normalization: int = 0
    lexical_weight: float = 1.0
    dense_weight: float = 1.0
    parent_weight: float = 0.0


@dataclass(frozen=True, slots=True)
class Hit:
    provision: Provision
    score: float
    explicit: bool = False


class SearchMode(StrEnum):
    HYBRID = "hybrid"  # full-text + vector, fused with RRF (default, ADR 0004)
    LEXICAL = "lexical"  # full-text only (benchmark baseline B0)
    DENSE = "dense"  # vector only (benchmark)


class RefusalReason(StrEnum):
    NONEXISTENT_PROVISION = "nonexistent_provision"
    LOW_SCORE = "low_score"


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: tuple[Hit, ...]
    best_similarity: float | None
    missing_references: tuple[str, ...] = field(default=())

    def refusal(self, threshold: float | None) -> RefusalReason | None:
        """Why retrieval alone says "no support in the corpus", or ``None`` (ADR 0005).

        An explicit reference that resolved to a provision always wins. A
        reference to a provision that does not exist ("art. 99 da LGPD")
        refuses. Otherwise, with a ``threshold``, the best dense similarity
        must reach it.
        """
        if any(hit.explicit for hit in self.hits):
            return None
        if self.missing_references:
            return RefusalReason.NONEXISTENT_PROVISION
        if threshold is not None and (
            self.best_similarity is None or self.best_similarity < threshold
        ):
            return RefusalReason.LOW_SCORE
        return None


class Retriever:
    def __init__(
        self,
        backend: SearchBackend,
        embedder: Embedder | None,
        *,
        candidate_pool: int = 50,
        mode: SearchMode = SearchMode.HYBRID,
        tuning: Tuning | None = None,
    ) -> None:
        if embedder is None and mode is not SearchMode.LEXICAL:
            raise ValueError(f"{mode.value} search needs a query embedder")
        self.backend = backend
        self.embedder = embedder
        self.candidate_pool = candidate_pool
        self.mode = mode
        self.tuning = tuning or Tuning()

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

        lexical: list[Ranked] = []
        dense: list[Ranked] = []
        tuning = self.tuning
        if self.mode is not SearchMode.DENSE:
            lexical = self.backend.lexical(
                question, self.candidate_pool, normalization=tuning.fts_normalization
            )
        if self.mode is not SearchMode.LEXICAL and self.embedder is not None:
            dense = self.backend.dense(self.embedder.embed_query(question), self.candidate_pool)
        rankings = [
            (ranking, weight)
            for ranking, weight in (
                ([r.provision_id for r in lexical], tuning.lexical_weight),
                ([r.provision_id for r in dense], tuning.dense_weight),
            )
            if ranking
        ]
        fused = reciprocal_rank_fusion([r for r, _ in rankings], weights=[w for _, w in rankings])
        if tuning.parent_weight:
            fused = propagate_to_ancestors(
                fused, self.backend.parents([pid for pid, _ in fused]), tuning.parent_weight
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
