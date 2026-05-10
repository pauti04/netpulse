"""Seed a focused BGP baseline for the 2024 Cloudflare 1.1.1.1 hijack benchmark.

Sources for the baseline values:
- Cloudflare's incident writeup:
  https://blog.cloudflare.com/cloudflare-1111-incident-on-june-27-2024/
- ARIN WHOIS for 1.1.1.0/24 lists APNIC as the IRR holder; it is operated
  by Cloudflare from AS13335 (verifiable via PeeringDB).

Usage:
    uv run python scripts/seed_cloudflare_baseline.py data/cloudflare_2024_baseline.duckdb
"""

from __future__ import annotations

import sys
from pathlib import Path

from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord

# Cloudflare's 1.1.1.0/24 is the supernet AS267613 announced 1.1.1.1/32 of.
BASELINE: list[tuple[str, int]] = [
    ("1.1.1.0/24", 13335),
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
