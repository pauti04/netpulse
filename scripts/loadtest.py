"""Concurrent load test for the NetPulse HTTP API.

Stdlib-only (no external load tool needed). Fires ``--requests`` POSTs to
``/detect/bgp`` across ``--concurrency`` worker threads and reports
latency percentiles + sustained throughput.

    # in one shell:  netpulse serve --store ... --baseline ...
    uv run python scripts/loadtest.py --url http://127.0.0.1:8000 \
        --requests 2000 --concurrency 32
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_PAYLOAD = json.dumps({"start_iso": "2008-02-24T18:45:00Z", "duration_s": 300}).encode()


def _one(url: str) -> tuple[float, int]:
    req = urllib.request.Request(
        f"{url}/detect/bgp", data=_PAYLOAD, headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
            status = resp.status
    except Exception:
        status = 0
    return (time.perf_counter() - t0) * 1000, status


def _pct(sorted_ms: list[float], p: float) -> float:
    if not sorted_ms:
        return 0.0
    idx = min(len(sorted_ms) - 1, int(p / 100 * len(sorted_ms)))
    return sorted_ms[idx]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--requests", type=int, default=2000)
    ap.add_argument("--concurrency", type=int, default=32)
    args = ap.parse_args()

    latencies: list[float] = []
    ok = 0
    wall0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for ms, status in pool.map(lambda _: _one(args.url), range(args.requests)):
            latencies.append(ms)
            ok += 1 if status == 200 else 0
    wall = time.perf_counter() - wall0

    latencies.sort()
    print(f"requests:     {args.requests}  (concurrency {args.concurrency})")
    print(f"success:      {ok}/{args.requests}")
    print(f"throughput:   {args.requests / wall:,.0f} req/sec  (wall {wall:.2f}s)")
    print(f"latency p50:  {_pct(latencies, 50):.1f} ms")
    print(f"latency p90:  {_pct(latencies, 90):.1f} ms")
    print(f"latency p99:  {_pct(latencies, 99):.1f} ms")
    print(f"latency max:  {latencies[-1]:.1f} ms")


if __name__ == "__main__":
    main()
