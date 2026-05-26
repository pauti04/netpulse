"""Seed a focused BGP baseline for the 2008 YouTube /24 sub-prefix hijack benchmark.

Pulling the full RRC00 RIB at 2008-02-24T16:00:00Z works but takes ~15-20
minutes of pure-Python iteration through pybgpstream — too slow to bake into
every benchmark run. This helper writes a minimal baseline containing only
the prefixes needed to evaluate the YouTube case, with origin ASNs sourced
from the cited RIPE NCC case study. Future work: a faster RIB ingest path.

Usage:
    uv run python scripts/seed_youtube_baseline.py data/youtube_2008_baseline.duckdb
"""

from __future__ import annotations

import sys
from pathlib import Path

from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord

# Source: https://www.ripe.net/publications/news/youtube-hijacking-a-ripe-ncc-ris-case-study/
# YouTube announced 208.65.152.0/22 from AS36561; AS17557's /24 hijack was a
# more-specific of that supernet.
BASELINE: list[tuple[str, int]] = [
    ("208.65.152.0/22", 36561),
]


def seed(out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    records = [
        BGPRecord(
            timestamp_us=0,
            collector="rrc00",
            peer_as=0,
            peer_ip="0.0.0.0",
            prefix=prefix,
            update_type="A",
            origin_as=origin_as,
            as_path=str(origin_as),
        )
        for prefix, origin_as in BASELINE
    ]
    with BGPStore(out_path) as store:
        return store.write_batch(records)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    written = seed(Path(sys.argv[1]))
    print(f"wrote {written} baseline records to {sys.argv[1]}")
