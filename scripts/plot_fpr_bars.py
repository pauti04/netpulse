"""Per-hour stacked bars: MOAS vs sub-prefix alert counts across the FPR survey.

Output: ``docs/img/fpr_per_hour.svg`` -- visual companion to the per-hour
table in BENCHMARK.md. Re-run after rerunning the FPR analysis.

Requires the ``[viz]`` extra (matplotlib).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "docs" / "img" / "fpr_per_hour.svg"

# (label, moas, subprefix) — exactly the run of run_fpr_analysis.py.
HOURS = [
    ("02-23 00:00\nbackground", 14, 0),
    ("02-24 06:00\nbackground", 145, 0),
    ("02-24 12:00\nbackground", 16, 0),
    ("02-24 18:00\nHIJACK", 10, 1),
    ("02-25 00:00\nbackground", 13, 0),
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    labels = [h[0] for h in HOURS]
    moas = [h[1] for h in HOURS]
    sub = [h[2] for h in HOURS]
    is_hijack = ["HIJACK" in lbl for lbl in labels]

    fig, ax = plt.subplots(figsize=(8.5, 4.2))

    x = list(range(len(labels)))
    moas_colors = ["#cc8888" if h else "#cccccc" for h in is_hijack]
    sub_colors = ["#cc3333" if h else "#888888" for h in is_hijack]

    ax.bar(
        x,
        moas,
        color=moas_colors,
        edgecolor="white",
        label="MOAS alerts (multi-origin prefixes; not all are hijacks)",
    )
    ax.bar(
        x,
        sub,
        bottom=moas,
        color=sub_colors,
        edgecolor="white",
        label="sub-prefix hijack alerts (true positives)",
    )

    for xi, m, s in zip(x, moas, sub, strict=True):
        if s > 0:
            ax.annotate(
                f"+{s}",
                xy=(xi, m + s),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=9,
                color="#cc3333",
                fontweight="bold",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("alerts in 1h window")
    ax.set_title(
        "BGP detector alerts by hour — RRC00, around the 2008-02-24 YouTube hijack",
        fontsize=11,
    )
    ax.legend(loc="upper right", framealpha=0.95, fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
