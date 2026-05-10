"""Run both BGP detectors over every hour-DuckDB in data/fpr/ and the YouTube hour.

Produces a per-hour table of alert counts plus an aggregate. The point is to
show:
- The sub-prefix detector fires only in the YouTube hour and never in the
  4 background hours -> 0 false positives across the surveyed window.
- The MOAS detector has a stable noise floor across hours, which is exactly
  why a supernet-aware detector is needed for hijack alerting.

Usage:
    uv run python scripts/run_fpr_analysis.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from netpulse.detectors.baseline import BGPBaseline
from netpulse.detectors.moas import MOASDetector
from netpulse.detectors.subprefix import SubPrefixHijackDetector
from netpulse.features.bgp import extract_bgp_features
from netpulse.storage.duckdb_store import BGPStore

REPO_ROOT = Path(__file__).resolve().parent.parent
FPR_DIR = REPO_ROOT / "data" / "fpr"
YOUTUBE_DUCKDB = REPO_ROOT / "data" / "youtube_2008.duckdb"

# (label, path, window_start_us, window_end_us)
WINDOWS: list[tuple[str, Path, int, int]] = [
    ("2008-02-23 00:00 UTC (background)", FPR_DIR / "fpr_2008_02_23_00.duckdb",
     1_203_724_800_000_000, 1_203_724_800_000_000 + 3_600_000_000),
    ("2008-02-24 06:00 UTC (background)", FPR_DIR / "fpr_2008_02_24_06.duckdb",
     1_203_832_800_000_000, 1_203_832_800_000_000 + 3_600_000_000),
    ("2008-02-24 12:00 UTC (background)", FPR_DIR / "fpr_2008_02_24_12.duckdb",
     1_203_854_400_000_000, 1_203_854_400_000_000 + 3_600_000_000),
    ("2008-02-24 18:00 UTC (HIJACK)", YOUTUBE_DUCKDB,
     1_203_876_000_000_000, 1_203_879_600_000_000),
    ("2008-02-25 00:00 UTC (background)", FPR_DIR / "fpr_2008_02_25_00.duckdb",
     1_203_897_600_000_000, 1_203_897_600_000_000 + 3_600_000_000),
]


@dataclass
class HourReport:
    label: str
    announces: int
    withdraws: int
    distinct_prefixes: int
    moas_alerts: int
    subprefix_alerts: int


def analyze_hour(label: str, path: Path, start_us: int, end_us: int,
                 baseline: BGPBaseline) -> HourReport | None:
    if not path.exists():
        print(f"  skip {label}: {path} not present")
        return None

    with BGPStore(path) as store:
        feats = extract_bgp_features(store, start_us, end_us)

    moas = MOASDetector().score(feats)
    sub = SubPrefixHijackDetector(baseline).score(feats)

    return HourReport(
        label=label,
        announces=feats.announce_total,
        withdraws=feats.withdraw_total,
        distinct_prefixes=len(feats.origins_by_prefix),
        moas_alerts=len(moas),
        subprefix_alerts=len(sub),
    )


def main() -> None:
    baseline = BGPBaseline.build({"208.65.152.0/22": {36561}})

    print(f"{'window':<40} {'ann':>8} {'wd':>6} {'pfxs':>7} {'moas':>5} {'sub':>4}")
    print("-" * 75)

    reports: list[HourReport] = []
    for label, path, start_us, end_us in WINDOWS:
        r = analyze_hour(label, path, start_us, end_us, baseline)
        if r is None:
            continue
        reports.append(r)
        print(
            f"{r.label:<40} {r.announces:>8} {r.withdraws:>6} "
            f"{r.distinct_prefixes:>7} {r.moas_alerts:>5} {r.subprefix_alerts:>4}"
        )

    print("-" * 75)
    if reports:
        total_pfxs = sum(r.distinct_prefixes for r in reports)
        total_moas = sum(r.moas_alerts for r in reports)
        total_sub = sum(r.subprefix_alerts for r in reports)
        background = [r for r in reports if "HIJACK" not in r.label]
        bg_sub = sum(r.subprefix_alerts for r in background)
        bg_pfxs = sum(r.distinct_prefixes for r in background)
        print(f"{'TOTAL':<40} {sum(r.announces for r in reports):>8} "
              f"{sum(r.withdraws for r in reports):>6} {total_pfxs:>7} "
              f"{total_moas:>5} {total_sub:>4}")
        print()
        print(f"sub-prefix FPR: {bg_sub} alerts on {bg_pfxs} prefixes "
              f"across {len(background)} background hours")
        print(f"MOAS noise floor: {total_moas / len(reports):.1f} alerts/hour mean")


if __name__ == "__main__":
    main()
