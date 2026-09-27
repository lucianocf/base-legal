"""Reciprocal Rank Fusion (Cormack et al., 2009)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

DEFAULT_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    k: int = DEFAULT_K,
    weights: Sequence[float] | None = None,
) -> list[tuple[str, float]]:
    """Fuse ranked ID lists (optionally weighted); ties break by best rank, then ID."""
    if k <= 0:
        raise ValueError("k must be positive")
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("one weight per ranking")
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for index, ranking in enumerate(rankings):
        weight = 1.0 if weights is None else weights[index]
        seen: set[str] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
            best_rank[item] = min(best_rank.get(item, rank), rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], best_rank[kv[0]], kv[0]))


def propagate_to_ancestors(
    ranked: Sequence[tuple[str, float]],
    parent_of: Mapping[str, str | None],
    weight: float,
) -> list[tuple[str, float]]:
    """Add ``weight ** depth`` of each item's score to each of its ancestors.

    Several matching incisos of one article are evidence that the question is
    about the article as a whole (ADR 0002: "parent-level questions need the
    caput plus its children"). Ancestors missing from ``ranked`` are added.
    Ties keep the input order.
    """
    if weight == 0:
        return list(ranked)
    scores = dict(ranked)
    order = {item: n for n, (item, _) in enumerate(ranked)}
    for item, score in ranked:
        parent, depth = parent_of.get(item), 1
        while parent is not None:
            scores[parent] = scores.get(parent, 0.0) + score * weight**depth
            order.setdefault(parent, len(order))
            parent, depth = parent_of.get(parent), depth + 1
    return sorted(scores.items(), key=lambda kv: (-kv[1], order[kv[0]]))
