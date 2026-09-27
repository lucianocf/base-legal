"""Retrieval metrics. Pure functions over ranked provision IDs."""

from __future__ import annotations

import math
from collections.abc import Sequence


def recall_at_k(expected: Sequence[str], ranked: Sequence[str], k: int) -> float:
    """Share of ``expected`` found in the top ``k`` of ``ranked``."""
    if not expected:
        raise ValueError("expected must not be empty")
    top = set(ranked[:k])
    return sum(1 for pid in expected if pid in top) / len(expected)


def hit_at_k(expected: Sequence[str], ranked: Sequence[str], k: int) -> bool:
    """Whether at least one expected provision is in the top ``k``."""
    top = set(ranked[:k])
    return any(pid in top for pid in expected)


def first_rank(expected: Sequence[str], ranked: Sequence[str]) -> int | None:
    """1-based rank of the first expected provision, or ``None``."""
    wanted = set(expected)
    for rank, pid in enumerate(ranked, start=1):
        if pid in wanted:
            return rank
    return None


def reciprocal_rank(expected: Sequence[str], ranked: Sequence[str]) -> float:
    rank = first_rank(expected, ranked)
    return 0.0 if rank is None else 1.0 / rank


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (``q`` in [0, 100]); deterministic, no interpolation."""
    if not values:
        raise ValueError("no values")
    if not 0 <= q <= 100:
        raise ValueError("q must be in [0, 100]")
    ordered = sorted(values)
    index = max(0, math.ceil(q / 100 * len(ordered)) - 1)
    return ordered[index]


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
