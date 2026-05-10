"""End-to-end multi-signal fusion demo on the 2018 MainOne route leak.

This is the demonstration of the project's "multi-signal" tagline:
two independent observability signals (BGP routing tables + RIPE Atlas
active probes) both fire on the same labeled incident, and the
correlator emits a single fused critical alert.

Reproduction (after `make install` and the BGP/Atlas extras are present):

    # 1. Pull 90 minutes of RRC00 transit-AS37282 routes (~60 s)
    netpulse ingest bgp \\
        --collector rrc00 --start 2018-11-12T21:00:00 --duration 90m \\
        --filter 'path "_37282_"' \\
        --out data/mainone_2018.duckdb

    # 2. Pull Atlas msm 1999544 (ping 8.8.8.8) for the same window
    netpulse ingest atlas --msm 1999544 \\
        --start 2018-11-12T21:00:00 --duration 90m \\
        --out data/mainone_2018_atlas.duckdb

    # 3. Pull the time-aligned CAIDA AS-relationships snapshot
    netpulse ingest asrel \\
        --source https://publicdata.caida.org/datasets/as-relationships/serial-2/20181101.as-rel2.txt.bz2 \\
        --out data/caida_asrel_2018_11.duckdb

    # 4. Run this demo
    uv run python scripts/fusion_demo.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from netpulse.detectors.fusion import MultiSignalCorrelator
from netpulse.detectors.route_leak import (
    ASRelationshipMap,
    ObservedPath,
    RouteLeakDetector,
    parse_as_path,
)
from netpulse.storage.asrel_store import ASRelStore
from netpulse.storage.duckdb_store import BGPStore

REPO_ROOT = Path(__file__).resolve().parent.parent
BGP_STORE = REPO_ROOT / "data" / "mainone_2018.duckdb"
ATLAS_STORE = REPO_ROOT / "data" / "mainone_2018_atlas.duckdb"
ASREL_STORE = REPO_ROOT / "data" / "caida_asrel_2018_11.duckdb"

# 2018-11-12  21:00 UTC --  21:06 UTC --              22:30 UTC
#             [---baseline---] [-- leak window (BGPmon onset 21:12) --]
WINDOW_START_US = int(1542056400 * 1_000_000)
BASELINE_END_US = int(1542056760 * 1_000_000)
WINDOW_END_US = int(1542061800 * 1_000_000)

ATTACKER_ASN = 37282  # MainOne (Nigeria)
VICTIM_ASN = 15169  # Google


def _bgp_signal() -> tuple[int, int, int]:
    """Run the route-leak detector. Returns (paths, total_alerts, mainone_alerts)."""
    with ASRelStore(ASREL_STORE) as store:
        rels = ASRelationshipMap.from_store(store)

    with BGPStore(BGP_STORE) as store:
        rows = store.query(
            "SELECT timestamp_us, prefix, peer_as, as_path FROM bgp_records "
            "WHERE update_type = 'A' AND as_path IS NOT NULL "
            "  AND timestamp_us >= ? AND timestamp_us < ?",
            [WINDOW_START_US, WINDOW_END_US],
        )

    paths = [
        ObservedPath(
            prefix=str(p),
            asns=parse_as_path(str(asp)) or [],
            peer_as=int(peer),
            timestamp_us=int(ts),
        )
        for ts, p, peer, asp in rows
        if parse_as_path(str(asp))
    ]

    alerts = RouteLeakDetector(rels=rels).score_paths(paths)
    mainone_alerts = [
        a
        for a in alerts
        if ATTACKER_ASN in a.evidence["path"] and VICTIM_ASN in a.evidence["path"]
    ]
    return len(paths), len(alerts), mainone_alerts


def _atlas_signal() -> tuple[float, float]:
    """Median RTT to 8.8.8.8 before vs during the leak window."""
    c = duckdb.connect(str(ATLAS_STORE), read_only=True)
    try:
        baseline = c.execute(
            "SELECT MEDIAN(avg_rtt_ms) FROM atlas_ping "
            "WHERE timestamp_us < ? AND avg_rtt_ms IS NOT NULL",
            [BASELINE_END_US],
        ).fetchone()[0]
        window = c.execute(
            "SELECT MEDIAN(avg_rtt_ms) FROM atlas_ping "
            "WHERE timestamp_us >= ? AND timestamp_us < ? AND avg_rtt_ms IS NOT NULL",
            [BASELINE_END_US, WINDOW_END_US],
        ).fetchone()[0]
    finally:
        c.close()
    return float(baseline), float(window)


def main() -> None:
    n_paths, n_total_alerts, mainone_alerts = _bgp_signal()
    baseline_rtt, window_rtt = _atlas_signal()

    fused = MultiSignalCorrelator(rtt_jump_factor=1.15).fuse(
        bgp_alerts=mainone_alerts,
        window_start_us=WINDOW_START_US,
        window_end_us=WINDOW_END_US,
        atlas_baseline_median_rtt_ms=baseline_rtt,
        atlas_window_median_rtt_ms=window_rtt,
        atlas_msm_id=1999544,
        atlas_target="8.8.8.8",
    )

    print("=" * 70)
    print("MULTI-SIGNAL FUSION  --  MainOne 2018 leak  --  REAL DATA")
    print("=" * 70)
    print()
    print("BGP signal (route_leak / CAIDA serial-2 20181101 snapshot):")
    print(f"  Paths inspected:                         {n_paths:>6,}")
    print(f"  Total leak-shape alerts:                 {n_total_alerts:>6,}")
    print(f"  MainOne-shape (path 37282 -> 15169):     {len(mainone_alerts):>6,}")
    print()
    print("Atlas signal (msm 1999544 ping 8.8.8.8):")
    print(f"  Baseline median RTT (pre-21:06Z):       {baseline_rtt:6.1f} ms")
    print(f"  Window   median RTT (21:06-22:30Z):     {window_rtt:6.1f} ms")
    print(f"  Ratio:                                  {window_rtt / baseline_rtt:6.2f}x")
    print()
    print("Fusion (rtt_jump_factor = 1.15x):")
    print(f"  FUSED ALERTS:                           {len(fused)}")
    for a in fused:
        print()
        print(f"  detector: {a.detector}")
        print(f"  severity: {a.severity}")
        print(f"  summary:  {a.summary}")


if __name__ == "__main__":
    main()
