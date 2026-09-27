"""Shields.io endpoint badges (https://shields.io/badges/endpoint-badge) for eval results."""

from __future__ import annotations

import json
from pathlib import Path


def badge(label: str, value: float, *, good: float, fair: float) -> dict[str, object]:
    """``value`` in [0, 1]; green at or above ``good``, yellow at or above ``fair``, else red."""
    color = "brightgreen" if value >= good else "yellow" if value >= fair else "red"
    return {"schemaVersion": 1, "label": label, "message": f"{100 * value:.0f}%", "color": color}


def write_badge(path: Path, label: str, value: float, *, good: float, fair: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = badge(label, value, good=good, fair=fair)
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
