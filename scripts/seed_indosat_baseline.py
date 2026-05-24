"""Seed a focused BGP baseline for the Indosat 2014-04-02 MOAS hijack.

On 2014-04-02 starting around 18:25 UTC, AS4761 (PT Indosat) briefly
re-announced ~417k prefixes globally that it does not own; BGPmon's
public write-up documents the same event.

Source: BGPmon, "BGP Hijack by Indosat" (Apr 2 2014). The Internet
Archive copy of the original BGPmon blog post is the authoritative
write-up for the event timing and scope.

The legitimate prefix -> origin mappings below were verified directly
from RRC00 RIB snapshots at 2014-04-02 16:00:00 UTC (90 minutes BEFORE
the hijack) and represent real APNIC delegations the corpus runner can
check against. Two ownership shapes are deliberately covered so that
SubPrefixHijackDetector exercises BOTH of its cases:

- exact-prefix matches (Case 1): 103.28.112.0/22, 124.40.248.0/21,
  202.56.164.0/22 are all owned by AS45305 (PT Cyberindo Aditama, an
  Indonesian ISP). Indosat re-announced these same /22s from AS4761,
  which is unambiguously unauthorized.
- sub-prefix matches (Case 2): 111.67.0.0/19 is owned by AS45454
  (XL Axiata, an Indonesian mobile carrier). Indosat re-announced
  /24 more-specifics inside that /19 from AS4761; SubPrefixHijack
  reaches them via its covering-supernet search.

Usage:
    uv run python scripts/seed_indosat_baseline.py \\
        data/baselines/indosat_2014_baseline.duckdb
"""

from __future__ import annotations

import sys
from pathlib import Path

from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord

# (prefix, legitimate_origin_asn). All verified against RRC00 RIB
# 2014-04-02T16:00:00Z. Order matters only for readability.
BASELINE: list[tuple[str, int]] = [
    # AS45305 (PT Cyberindo Aditama). Three /22s Indosat re-announced
    # at the same length, so SubPrefixHijack fires on the exact-prefix
    # shape (Case 1).
    ("103.28.112.0/22", 45305),
    ("124.40.248.0/21", 45305),
    ("202.56.164.0/22", 45305),
    # AS45454 (XL Axiata). Indosat re-announced /24 more-specifics
    # inside this /19; SubPrefixHijack catches them via the
    # covering-supernet path (Case 2).
    ("111.67.0.0/19", 45454),
    # AS45348. Same /19-supernet trick for the .96-.127 portion of
    # 111.67/x.
    ("111.67.96.0/19", 45348),
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
