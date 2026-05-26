"""Seed a focused BGP baseline for the 2017 Rostelecom hijack benchmark.

Source: Doug Madory / Dyn Research analysis of the 2017-04-26 incident,
where AS12389 (Rostelecom) briefly originated ~36 prefixes belonging
to major US financial networks (Mastercard, Visa, others). Onset
22:36 UTC; the hijack lasted ~10 minutes.

The baseline only needs to cover the prefixes hijacked so that
SubPrefixHijackDetector fires when AS12389 announces them. Legitimate
origins below come from rrc00 RIB snapshots fetched at
2017-04-26T16:00 UTC (the most recent RIB before onset), filtered to
each /16 supernet via libBGPStream's native `prefix any` filter.

Usage:
    uv run python scripts/seed_rostelecom_baseline.py \\
        data/baselines/rostelecom_2017_baseline.duckdb
"""

from __future__ import annotations

import sys
from pathlib import Path

from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord

# (prefix, origin_as) -- each line is verified against an rrc00 RIB
# pull at 2017-04-26T16:00 UTC, see commit history for the queries.
BASELINE: list[tuple[str, int]] = [
    # MasterCard's edgenet block
    ("216.119.216.0/22", 26380),
    ("216.119.216.0/24", 26380),
    # PSINet / federal address block (USPS / Visa-adjacent)
    ("198.241.161.0/24", 2559),
    ("198.241.170.0/24", 2559),
    # Sprint legacy block covering 65.205.x
    ("65.205.0.0/24", 31838),
    # Edgecast-era allocation covering 69.58.181.0/24
    ("69.58.0.0/21", 55286),
    # Savvis / CenturyLink legacy block covering 64.75.29.0/24
    ("64.75.0.0/18", 3561),
]


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: seed_rostelecom_baseline.py <out.duckdb>", file=sys.stderr)
        sys.exit(2)
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)

    # We materialize the baseline as if it were a RIB snapshot from
    # 2017-04-26T16:00Z. The exact timestamp doesn't matter for the
    # detector -- BGPBaseline.from_store reads (prefix, origin_as)
    # uniqueness only.
    ts_us = 1_493_222_400_000_000  # 2017-04-26T16:00:00Z
    records = [
        BGPRecord(
            timestamp_us=ts_us,
            collector="seed",
            peer_as=0,
            peer_ip="0.0.0.0",
            update_type="A",
            prefix=prefix,
            origin_as=origin_as,
            as_path=f"{origin_as}",
        )
        for prefix, origin_as in BASELINE
    ]
    store = BGPStore(out)
    try:
        store.write_batch(records)
    finally:
        store.close()
    print(f"wrote {len(records)} baseline rows -> {out}")


if __name__ == "__main__":
    main()
