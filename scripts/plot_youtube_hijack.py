"""Plot AS17557 announcements of 208.65.153.0/24 around the documented onset.

Produces ``docs/img/youtube_2008_onset.svg`` from the bundled demo fixture.
Re-run after editing the fixture or the plot styling.

Requires the ``[viz]`` extra (matplotlib).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "data" / "fixtures" / "youtube_2008_demo.duckdb"
OUT = REPO_ROOT / "docs" / "img" / "youtube_2008_onset.svg"

# Documented onset: first AS17557 announcement of /24 observed at RRC00.
ONSET = datetime(2008, 2, 24, 18, 47, 57, tzinfo=UTC)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(FIXTURE), read_only=True)

    # Per-second announce counts for the hijacked /24 from AS17557.
    rows = con.execute(
        """
        SELECT
            CAST(timestamp_us / 1000000 AS BIGINT) AS sec,
            COUNT(*) AS n
        FROM bgp_records
        WHERE prefix = '208.65.153.0/24' AND origin_as = 17557
        GROUP BY sec
        ORDER BY sec
        """
    ).fetchall()

    # Per-second announce counts for any other prefix in the same window
    # (background floor for visual context).
    bg_rows = con.execute(
        """
        SELECT
            CAST(timestamp_us / 1000000 AS BIGINT) AS sec,
            COUNT(*) AS n
        FROM bgp_records
        WHERE prefix != '208.65.153.0/24'
        GROUP BY sec
        ORDER BY sec
        """
    ).fetchall()
    con.close()

    times = [datetime.fromtimestamp(s, tz=UTC) for s, _ in rows]
    counts = [n for _, n in rows]

    bg_times = [datetime.fromtimestamp(s, tz=UTC) for s, _ in bg_rows]
    bg_counts = [n for _, n in bg_rows]

    fig, ax = plt.subplots(figsize=(9, 4))

    ax.bar(
        bg_times,
        bg_counts,
        width=timedelta(seconds=1),
        color="#cccccc",
        label="other prefixes (background)",
        zorder=1,
    )
    ax.bar(
        times,
        counts,
        width=timedelta(seconds=1),
        color="#cc3333",
        label="208.65.153.0/24 from AS17557 (the hijack)",
        zorder=3,
    )
    ax.axvline(ONSET, color="#222222", linewidth=1.0, linestyle="--", zorder=2)
    ax.annotate(
        f"onset {ONSET.strftime('%H:%M:%S')}Z",
        xy=(ONSET, ax.get_ylim()[1] * 0.95),
        xytext=(8, -2),
        textcoords="offset points",
        fontsize=9,
        color="#222222",
    )

    ax.set_title(
        "2008 YouTube /24 sub-prefix hijack at RRC00 — announces per second",
        fontsize=11,
    )
    ax.set_ylabel("announces / sec")
    ax.set_xlabel("UTC")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
    ax.legend(loc="upper left", framealpha=0.95)
    ax.grid(axis="y", alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
