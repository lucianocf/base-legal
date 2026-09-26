"""Reciprocal Rank Fusion (Cormack et al., 2009)."""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], k: int = DEFAULT_K
) -> list[tuple[str, float]]:
    """Fuse ranked ID lists; ties break by best individual rank, then ID."""
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            best_rank[item] = min(best_rank.get(item, rank), rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], best_rank[kv[0]], kv[0]))
