# Performance

All numbers are reproducible with the scripts named below, on an Apple
M-series laptop (single machine). They are wall-clock, best-of-5 after a
warm-up, and the commands are committed so you can re-run them.

## 1. Detection-pipeline throughput

The hot path is `extract_bgp_features` (a DuckDB `GROUP BY`) followed by
the detector bank (MOAS + sub-prefix + origin-deaggregation).

**On a real 131,562-record RIPE RIS window (`rrc00`, Indosat 2014):**

| Stage | Before | After |
| ----- | -----: | ----: |
| Sub-prefix detector | 240.6 ms | **20.0 ms** (12×) |
| End-to-end pipeline | 420K rec/s | **1.71M rec/s** (4×) |

**Reproducible synthetic benchmark** (`scripts/bench_throughput.py`, no
vendored capture needed — deterministic adversarial-heavy data):

```
   records   feat ms  detect ms  total ms   records/sec
    10,000       9.7       10.0      19.7       506,561
   100,000     132.7      156.7     289.4       345,490
   500,000     631.5      752.8    1384.4       361,180
```

Scaling is ~linear in record count. The synthetic set is intentionally
anomaly-heavy (15% MOAS / sub-prefix conflicts) so the detectors do more
work than on real traffic — it's a floor, not a ceiling.

### The optimization

Profiling showed `ipaddress.ip_network()` octet parsing dominated CPU
(~190 ms of the 240 ms sub-prefix cost): every prefix string was parsed
**twice per call** (exact-match lookup + supernet walk) and **again on
every run**. The fix is a bounded module-level `lru_cache`
(`_parse_network` in `detectors/baseline.py`) that parses each distinct
prefix once for the process lifetime — 92% cache hit rate on the real
window, behaviour unchanged (the 7 sub-prefix tests pass as-is).

```sh
uv run python scripts/bench_throughput.py
```

## 2. HTTP API under load

`POST /detect/bgp` runs a full feature-extraction + detection per request
(not a toy echo). Measured with `scripts/loadtest.py` (stdlib, no
external load tool).

| Configuration | Throughput | p50 | p99 | Success |
| ------------- | ---------: | --: | --: | ------: |
| `/detect`, concurrency 1 | 36 req/s | 27.8 ms | 32.8 ms | 100% |
| `/detect`, 1 worker, c=8 | ~104 req/s | 73.9 ms | 160.8 ms | 100% |
| `/detect`, **4 workers**, c=32 | **390 req/s** | 74.9 ms | 200.1 ms | 100% |
| `/health` (no compute), c=64 | 1,830 req/s | 33.3 ms | 52.8 ms | 100% |

**Per-request latency is 28 ms p50** — tight and predictable. A single
worker is CPU-bound (Python GIL + per-request detection), so it saturates
one core at ~104 req/s; the endpoint is stateless, so throughput scales
**~linearly with workers (3.75× on 4)**.

```sh
netpulse serve --store data/fixtures/youtube_2008_demo.duckdb \
               --baseline data/baselines/yt_rib_filtered.duckdb --workers 4
uv run python scripts/loadtest.py --requests 3000 --concurrency 32
```

### A concurrency bug load-testing caught

The first 4-worker run returned **only 586/3000 successes**. Root cause:
DuckDB acquires a **read-write file lock** on open, so only one of the
four worker processes could open the store — the other three failed every
request. Fix: `BGPStore(..., read_only=True)` on all serving paths (the
write lock isn't needed to query), which lets every worker share the file.
After the fix: **3000/3000**. This is the kind of issue that only shows up
under concurrent load, which is why the load test is part of the repo.

## 3. RPKI origin validation

RFC 6811 origin validation against a real 859K-VRP set, via a
longest-prefix-match index instead of a linear scan over covering
networks: **~43 µs/call (~23K validations/sec)**, a 500× speedup over the
naive scan. Methodology in [BENCHMARK.md](BENCHMARK.md#performance).

## How to reproduce everything

```sh
uv sync
uv run python scripts/bench_throughput.py            # §1
# in one shell:
netpulse serve --store data/fixtures/youtube_2008_demo.duckdb \
               --baseline data/baselines/yt_rib_filtered.duckdb --workers 4
# in another:
uv run python scripts/loadtest.py --requests 3000 --concurrency 32   # §2
```
