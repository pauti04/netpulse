"""Throughput benchmark for the BGP detection pipeline.

Generates a deterministic synthetic BGP window (realistic mix of normal
announcements, MOAS conflicts, and /24 sub-prefixes of announced /22s),
then measures end-to-end throughput: DuckDB feature extraction +
MOAS + sub-prefix + origin-deaggregation detectors.

Synthetic data keeps the benchmark reproducible on any clone / in CI
without depending on a multi-megabyte vendored capture. Numbers on real
RIPE RIS data are in PERFORMANCE.md.

    uv run python scripts/bench_throughput.py
    uv run python scripts/bench_throughput.py --sizes 10000,100000,500000
"""

from __future__ import annotations

import argparse
import random
import tempfile
import time
from pathlib import Path

from netpulse.detectors.baseline import BGPBaseline
from netpulse.detectors.moas import MOASDetector
from netpulse.detectors.origin_deaggregation import OriginDeaggregationDetector
from netpulse.detectors.subprefix import SubPrefixHijackDetector
from netpulse.features.bgp import extract_bgp_features
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord

_SEED = 1337


def _synthesize(n: int) -> list[BGPRecord]:
    """Deterministic synthetic BGP records with realistic anomaly shapes."""
    rng = random.Random(_SEED)
    records: list[BGPRecord] = []
    base_ts = 1_700_000_000_000_000
    for i in range(n):
        a, b = rng.randrange(1, 224), rng.randrange(0, 256)
        roll = rng.random()
        if roll < 0.05:
            # MOAS: same /22 from a second origin.
            prefix = f"{a}.{b}.0.0/22"
            origin = rng.choice([64500, 64501])
        elif roll < 0.15:
            # /24 sub-prefix of an announced /22 from a different origin.
            prefix = f"{a}.{b}.{rng.randrange(0, 4)}.0/24"
            origin = rng.randrange(65000, 65100)
        else:
            prefix = f"{a}.{b}.0.0/22"
            origin = rng.randrange(1000, 60000)
        path_len = rng.randrange(2, 7)
        path = " ".join(str(rng.randrange(1, 65000)) for _ in range(path_len - 1)) + f" {origin}"
        records.append(
            BGPRecord(
                timestamp_us=base_ts + i,
                collector="bench",
                peer_as=rng.randrange(1, 400),
                peer_ip="192.0.2.1",
                prefix=prefix,
                update_type="A",
                origin_as=origin,
                as_path=path,
            )
        )
    return records


def _bench_size(n: int, tmp: Path) -> dict[str, float]:
    store_path = tmp / f"bench_{n}.duckdb"
    with BGPStore(store_path) as store:
        store.write_batch(_synthesize(n))
        lo, hi = store.query("SELECT MIN(timestamp_us), MAX(timestamp_us) FROM bgp_records")[0]
        detectors = [
            MOASDetector(),
            SubPrefixHijackDetector(BGPBaseline.build({})),
            OriginDeaggregationDetector(),
        ]

        # Warm-up (fills the prefix-parse cache, JITs nothing but stabilizes).
        feats = extract_bgp_features(store, int(lo), int(hi) + 1)
        for d in detectors:
            d.score(feats)

        best_feat = best_total = 1e9
        for _ in range(5):
            t0 = time.perf_counter()
            feats = extract_bgp_features(store, int(lo), int(hi) + 1)
            t1 = time.perf_counter()
            for d in detectors:
                d.score(feats)
            t2 = time.perf_counter()
            best_feat = min(best_feat, t1 - t0)
            best_total = min(best_total, t2 - t0)
    return {
        "records": n,
        "feat_ms": best_feat * 1000,
        "detect_ms": (best_total - best_feat) * 1000,
        "total_ms": best_total * 1000,
        "rec_per_sec": n / best_total,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sizes", default="10000,100000,500000")
    args = ap.parse_args()
    sizes = [int(s) for s in args.sizes.split(",")]

    print(f"{'records':>10}{'feat ms':>10}{'detect ms':>11}{'total ms':>10}{'records/sec':>14}")
    print("-" * 55)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for n in sizes:
            r = _bench_size(n, tmp)
            print(
                f"{r['records']:>10,}{r['feat_ms']:>10.1f}{r['detect_ms']:>11.1f}"
                f"{r['total_ms']:>10.1f}{r['rec_per_sec']:>14,.0f}"
            )


if __name__ == "__main__":
    main()
