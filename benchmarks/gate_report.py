"""Render docs/evals/embedding-gate.md from reports/gate/B*.json (embedding_gate.py)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
GATE = ROOT / "reports" / "gate"
ORDER = ("B0", "B1", "B2", "B3", "B4")


def main() -> None:
    rows: dict[tuple[str, str, str], dict[str, float]] = {}
    configs: dict[str, dict[str, str]] = {}
    for name in ORDER:
        path = GATE / f"{name}.json"
        if not path.exists():
            continue
        for report in json.loads(path.read_text(encoding="utf-8")):
            mode = report["config"]["mode"]
            configs[name] = report["config"]
            rows[(name, mode, report["split"])] = report["metrics"]

    lines = [
        "| Config | Documents | Questions | Mode | recall@5 dev | recall@5 holdout "
        "| recall@5 all | MRR all | p50 / p95 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name in ORDER:
        for mode in ("lexical", "dense", "hybrid"):
            if (name, mode, "all") not in rows:
                continue
            dev, hold, every = (rows[(name, mode, s)] for s in ("dev", "holdout", "all"))
            config = configs[name]
            lines.append(
                f"| {name} | {config['documents']} | {config['queries']} | {mode} "
                f"| {100 * dev['recall_at_5']:.1f} % | {100 * hold['recall_at_5']:.1f} % "
                f"| {100 * every['recall_at_5']:.1f} % | {every['mrr']:.3f} "
                f"| {every['latency_p50_ms']:.0f} / {every['latency_p95_ms']:.0f} ms |"
            )
    print("\n".join(lines))
    b1 = rows.get(("B1", "hybrid", "all"))
    b3 = rows.get(("B3", "hybrid", "all"))
    if b1 and b3:
        delta = 100 * (b3["recall_at_5"] - b1["recall_at_5"])
        verdict = "adopt B3 (new ADR needed)" if delta > 3 else "keep B1"
        print(f"\nADR 0003 rule: B3 minus B1 hybrid recall@5 = {delta:+.1f} points → {verdict}")
    hybrid = {n: rows[(n, "hybrid", "all")] for n in ORDER if (n, "hybrid", "all") in rows}
    if hybrid:
        best = max(hybrid, key=lambda n: (hybrid[n]["recall_at_5"], hybrid[n]["mrr"]))
        print(f"Best hybrid recall@5 (all): {best} ({100 * hybrid[best]['recall_at_5']:.1f} %)")


if __name__ == "__main__":
    main()
