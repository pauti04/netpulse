"""Extract a small slice of a real RIS pull as a committed demo fixture.

This produces ``data/fixtures/youtube_2008_demo.duckdb`` (~500 KB) — the
five minutes of RRC00 around the YouTube hijack onset, covering 424
prefixes including the hijacked /24. Re-run if the source data changes.

Usage:
    uv run python scripts/extract_demo_fixture.py \\
        data/youtube_2008.duckdb data/fixtures/youtube_2008_demo.duckdb
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

# 2008-02-24 18:45:00 UTC ... 18:50:00 UTC (covers the 18:47:57 UTC onset)
WINDOW_START_US = 1_203_878_700_000_000
WINDOW_END_US = 1_203_879_000_000_000


def extract(src_path: Path, dst_path: Path) -> int:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.unlink(missing_ok=True)
    dst_path.with_suffix(dst_path.suffix + ".wal").unlink(missing_ok=True)

    src = duckdb.connect(str(src_path), read_only=True)
    dst = duckdb.connect(str(dst_path))
    dst.execute(
        """
        CREATE TABLE bgp_records (
            timestamp_us BIGINT NOT NULL,
            collector    VARCHAR NOT NULL,
            peer_as      BIGINT NOT NULL,
            peer_ip      VARCHAR NOT NULL,
            prefix       VARCHAR NOT NULL,
            origin_as    BIGINT,
            as_path      VARCHAR,
            update_type  VARCHAR NOT NULL,
            communities  VARCHAR
        )
        """
    )
    rows = src.execute(
        """
        SELECT timestamp_us, collector, peer_as, peer_ip, prefix,
               origin_as, as_path, update_type, communities
        FROM bgp_records
        WHERE timestamp_us >= ? AND timestamp_us < ?
        """,
        [WINDOW_START_US, WINDOW_END_US],
    ).fetchall()
    dst.executemany("INSERT INTO bgp_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    dst.execute("CHECKPOINT")
    dst.close()
    src.close()
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    n = extract(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"extracted {n} records to {sys.argv[2]}")
