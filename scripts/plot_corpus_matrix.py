"""Render the corpus benchmark JSON as a chart.

Consumes ``docs/corpus_benchmark.json`` produced by
``run_corpus_benchmark.py`` and writes ``docs/img/corpus_matrix.svg``.
The chart is a horizontal bar per incident showing on-target alerts
(green) vs other alerts in the same window (grey), with the outcome
(TP / FN / GAP) annotated.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

REPO_ROOT = Path(__file__).resolve().parent.parent
IN_PATH = REPO_ROOT / "docs" / "corpus_benchmark.json"
OUT_PATH = REPO_ROOT / "docs" / "img" / "corpus_matrix.svg"


_OUTCOME_COLOR = {
    "TP": "#2e8b57",  # green
    "FN": "#c0392b",  # red
    "GAP": "#d4a017",  # amber
}


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(IN_PATH.read_text())
    results = data["results"]
    if not results:
        print("no results in corpus_benchmark.json")
        return

    # Order: TPs first, then GAPs, then FNs; alphabetical inside each.
    order = {"TP": 0, "GAP": 1, "FN": 2}
    results.sort(key=lambda r: (order.get(r["outcome"], 9), r["incident_id"]))

    labels = [f"{r['incident_id']}\n({r['shape']})  ·  {r['expected_detector']}" for r in results]
    on_target = [r["on_target_alerts"] for r in results]
    other = [r["other_alerts"] for r in results]
    outcomes = [r["outcome"] for r in results]

    fig, ax = plt.subplots(figsize=(11.5, max(3.6, 0.9 * len(results) + 1.8)))

    ys = list(range(len(results)))
    # On-target alerts in green if TP, amber if GAP (zero anyway), red if FN.
    on_colors = [_OUTCOME_COLOR.get(o, "#888888") for o in outcomes]
    # log scale would crush single-alert TPs; use linear and a min display
    display_on = [max(v, 0) for v in on_target]
    display_other = [max(v, 0) for v in other]

    ax.barh(
        ys,
        display_on,
        color=on_colors,
        edgecolor="white",
        label="on-target alerts (right shape, right entity)",
    )
    ax.barh(
        ys,
        display_other,
        left=display_on,
        color="#bdbdbd",
        edgecolor="white",
        label="other alerts in the same window",
    )

    # Annotations: outcome + numeric breakdown
    for y, r in enumerate(results):
        total = r["on_target_alerts"] + r["other_alerts"]
        annotation = (
            f"  {r['outcome']}  ({r['on_target_alerts']} on-target, {r['other_alerts']} other)"
        )
        ax.annotate(
            annotation,
            xy=(max(total, 1), y),
            va="center",
            ha="left",
            fontsize=9,
            color={"TP": "#2e8b57", "FN": "#c0392b", "GAP": "#b8860b"}.get(r["outcome"], "#444"),
            fontweight="bold",
        )

    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xscale("symlog", linthresh=10)
    ax.set_xlabel("alerts in the labeled-incident window (symlog scale)")
    ax.set_title(
        f"NetPulse corpus benchmark — {data['tp']}/{data['total']} TP  "
        f"+ {data['gap']} GAP  ({(data['tp'] + data['gap']) / data['total']:.0%} coverage)",
        fontsize=12,
    )

    legend_handles = [
        Patch(facecolor="#2e8b57", label="TP — detector fired on the labeled victim"),
        Patch(facecolor="#d4a017", label="GAP — detector exists, data-coverage limitation"),
        Patch(facecolor="#c0392b", label="FN — detector should fire but did not"),
        Patch(facecolor="#bdbdbd", label="other alerts in the same window"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", framealpha=0.95, fontsize=9)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_PATH)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
