# NetPulse: An Open, Reproducible Benchmark for BGP Anomaly Detection

*Working note, v0.4. Living document — every claim has a `BENCHMARK.md`
reference and a re-run command in this repository.*

## Abstract

We describe NetPulse, an open-source detector for BGP anomalies
(sub-prefix hijacks, multi-origin events, route leaks, RPKI-invalid
announcements) packaged with a public, reproducible benchmark on labeled
historical incidents and on a controlled false-positive survey of
neighboring time windows. Across a 4-incident corpus assembled from
RIPE RIS archive data, NetPulse's expected detector reaches the
incident in 3/4 cases; the fourth case is an honest miss explained by a
gap in the public CAIDA serial-2 inferred-relationships data for that
month. On the two sub-prefix incidents we report a streaming-mode
detection latency of 0 µs from documented onset, measured per record,
and a 1-alert / 0-FP outcome in the hijack hour against a real
RIB-derived baseline that emits zero alerts across four background
hours. The contribution is not a new detection algorithm: it is the
combination of an end-to-end open implementation, a transparent
methodology, a single-file replay harness, and a per-incident outcome
table with reproduction commands, evaluated against primary-source data.

## 1. Background and motivation

BGP anomaly detection has been studied for two decades. The canonical
academic systems (PHAS [Lad06], Pretty Good BGP [Karlin06], ARTEMIS
[Sermpezis18]) describe credible detection pipelines, and operator-facing
services (BGPmon, Cisco Crosswork, Cloudflare Radar, Kentik, ThousandEyes)
ship production telemetry. Public benchmarks comparing these tools on
the same labeled incidents are essentially absent: the closest we have
are per-paper case studies on hand-picked events, with the data and
configurations that produced them rarely published in a re-runnable
form.

NetPulse does not attempt a head-to-head comparison with these tools.
It targets a smaller, more verifiable claim: *a small open detector
suite, run on real archived RIS data with primary-source labels, can
deliver well-characterized precision, recall, and latency numbers that a
reader can rerun in minutes*. The benchmark is the contribution; the
detector logic is intentionally textbook.

## 2. System overview

```
ingest -> storage -> features -> detectors -> alerts -> (publishers | api | benchmark)
```

- **Ingest.** `pybgpstream` (libBGPStream wrapper) for RIPE RIS and
  RouteViews, including native pre-filtering (`prefix any …`, `path …`),
  RIPE Atlas (`cousteau` / `sagan`) for active probe measurements,
  Cloudflare's rpki.json export for RFC 6480 VRPs, and CAIDA's
  serial-2 inferred AS relationships for route-leak detection.
- **Storage.** DuckDB single-file stores, one per stream. A read-only
  `MultiStoreBGPView` ATTACHes N stores and exposes a UNION ALL view so
  detectors can see evidence from multiple collectors at zero copy.
- **Features.** Stateless extraction over a half-open `[start_us, end_us)`
  window: per-prefix origin sets, announce/withdraw counts.
- **Detectors.** Five total today:
  - `moas`: any multi-origin prefix in the window.
  - `subprefix_hijack`: a more-specific (or exact prefix) announced from
    an origin not authorized for the covering supernet.
  - `withdraw_spike`: high withdraw-to-announce ratio in the window.
  - `route_leak`: valley-free violations on observed AS-paths
    (RFC 7908 Type-1) classified against CAIDA serial-2 relationships.
  - `rpki_invalid`: RFC 6811 origin validation against a VRP set,
    using longest-prefix-match (~43 µs/call against 859k VRPs).
- **Alerts.** `Alert` dataclass with stdout/JSON/history publishers
  and cooldown-based deduplication.
- **Benchmark.** Replay harness with two latency reporting modes
  (chunk-bounded expanding-window and per-record streaming) and a
  corpus runner that produces TP / FN / GAP per incident.
- **API.** FastAPI exposing `/detect/bgp`, `/alerts`, `/health`,
  `/metrics` (Prometheus text-format).

## 3. Methodology

### 3.1 Incident corpus

Four incidents are labeled today, populated only from primary sources
(RIPE NCC case studies, Cloudflare/BGPmon writeups, ISC reports).
Hard rule in the repository: no AI-generated or extrapolated incident
data is ever committed. Each fixture cites its source URL.

| Incident                          | Date          | Shape                  | Source                            |
| --------------------------------- | ------------- | ---------------------- | --------------------------------- |
| YouTube / Pakistan                | 2008-02-24    | sub-prefix hijack      | RIPE NCC RIS case study           |
| MyEtherWallet                     | 2018-04-24    | sub-prefix hijack      | Cloudflare BGP-leaks blog         |
| MainOne → Google                  | 2018-11-12    | route leak (RFC 7908)  | BGPmon / ThousandEyes writeups    |
| Google → Verizon → NTT            | 2017-08-25    | route leak (RFC 7908)  | NTT / ISC operator reports        |

The 2024-06-27 Cloudflare 1.1.1.1 incident is documented in this
benchmark but **not** labeled, because cross-collector inspection
(8 RIS collectors, targeted libBGPStream filter) showed the host-route
`/32` did not reach any RIS-monitored peer.

### 3.2 Detector evaluation outcomes

Outcomes are reported per incident in three buckets:

- **TP** — the expected detector fired on the incident's distinguishing
  evidence.
- **FN** — the expected detector did not fire and the evidence in the
  archive should have caused it to.
- **GAP** — the expected detector did not fire because a *necessary
  exogenous input* (e.g. a time-aligned CAIDA snapshot covering the
  relevant AS pair) is unavailable. We do not credit these as detections,
  but they are not algorithm failures either, and the writeup names the
  missing input.

Current corpus result (`docs/corpus_benchmark.json`,
`docs/img/corpus_matrix.svg`):

```
N=4    TP=3    FN=0    GAP=1
```

The GAP is the Google 2017 leak: the CAIDA 2017-08 snapshot does not
contain an inferred relationship for AS15169 ↔ AS4713, so the
valley-free analyzer abstains on that pair rather than guessing.
Detector logic on this incident is unchanged from the MainOne 2018
case where it fires.

### 3.3 False-positive survey

For sub-prefix detection we report the per-hour alert count across
five contiguous hours of real RRC00 data around the YouTube incident,
two before and two after. A single alert fires across the five-hour
window, in the hour the hijack occurred. The detector runs against an
**actual RIB-derived baseline** (89 covering supernets in `208.65.0.0/16`
from RRC00's 16:00 UTC dump on 2008-02-24, pulled in 47 s with the
native libBGPStream filter), not a hand-curated row.

| Hour          | MOAS alerts | Sub-prefix alerts | Comment             |
| ------------- | ----------: | ----------------: | ------------------- |
| 2008-02-23 00 |          14 |                 0 | background          |
| 2008-02-24 06 |         145 |                 0 | background          |
| 2008-02-24 12 |          16 |                 0 | background          |
| 2008-02-24 18 |          10 |             **1** | hijack hour         |
| 2008-02-25 00 |          13 |                 0 | background          |

The MOAS row is intentionally retained — same-prefix multi-origin
events are common (anycast, multi-homed customers) and the row is the
empirical case for needing a *supernet-aware* detector, which is
exactly the shape of the YouTube hijack.

### 3.4 Latency

Two numbers are reported, both against the same archive data.
*Chunk-bounded* latency is the right edge of the first expanding-window
chunk in which the detector fires (parameterized by `--chunk`).
*Streaming-mode* latency is the per-record delta from documented
`onset_us` to the first qualifying update.

| Incident                  | Chunk-bounded (`--chunk 1m`) | Streaming-mode (per-record) |
| ------------------------- | ---------------------------: | --------------------------: |
| YouTube / Pakistan 2008   |                         3.0s |                  **0.000s** |
| MyEtherWallet 2018        |                         3.0s |                  **0.000s** |

The streaming row is 0 µs because, in the public RIS archive, the
first record satisfying the per-record sub-prefix check is the
documented onset record itself (the timestamps in the fixture JSON
are derived from that record, not from external reporting). The
chunk-bounded number is the bound an operator would hit in batch-style
replay; the streaming number is the bound the same logic delivers on
an update stream.

### 3.5 Performance

Reported per-operation throughput on the bundled fixtures:

| Operation                                                          | Throughput / latency           |
| ------------------------------------------------------------------ | -----------------------------: |
| Ingest 1 h of 2008 RRC00 BGP updates (no filter, ~57k records)     | ~80 s                          |
| Ingest 5 min `route-views2` filtered to `208.65.0.0/16`            | ~3.6 s for 71 records          |
| Ingest 859k RPKI VRPs (DuckDB-native bulk load)                    | ~20 s                          |
| Ingest 739k–1.1M CAIDA serial-2 inferred relationships              | ~7 s                           |
| Feature extraction over a 1 h / 51k-announce / 7.7k-prefix window  | **39 ms**                      |
| Sub-prefix detector across 7.7k prefixes vs 89-row baseline        | **267 ms**                     |
| Route-leak detector across 1,000 real archived AS-paths            | **5.7 ms** (0.006 ms / path)   |
| RPKI validate(prefix, asn) against 859k VRPs                       | **43 µs / call** (~23k / sec)  |

The RPKI validator was reduced from ~22 ms to ~43 µs per call by
replacing a linear scan of all covering networks with longest-prefix-
match against a single canonical-network dict (33 lookups for IPv4,
each O(1) — same RFC 6811 §2 Cover/Match correctness, **500× faster**).

## 4. Multi-signal correlation

The "multi-signal" framing is implemented as one minimal correlator,
not a fusion framework. `MultiSignalCorrelator` takes three inputs —
BGP alerts in a window, Atlas baseline median RTT, Atlas window median
RTT — and emits a single fused critical alert when a BGP anomaly
co-occurs with an Atlas RTT jump above a threshold.

End-to-end on real data for the MainOne 2018 leak:

```
BGP signal (route_leak / CAIDA 20181101 snapshot):
  Paths inspected:                         7,411
  Total leak-shape alerts:                 2,591
  MainOne-shape (path 37282 -> 15169):     1,985

Atlas signal (msm 1999544 ping 8.8.8.8):
  Baseline median RTT (pre-21:06Z):         38.0 ms
  Window   median RTT (21:06-22:30Z):       49.9 ms
  Ratio:                                    1.31x

Fusion (rtt_jump_factor = 1.15x):
  FUSED ALERTS:                            1
```

Reproducible end-to-end with `scripts/fusion_demo.py`. The leak detector
requires the *time-aligned* CAIDA snapshot (`20181101.as-rel2`); the
current snapshot has too much temporal drift and emits only generic
alerts. That sensitivity to the relationships table being time-aligned
is itself a methodology point — a deployment claiming generic leak
detection without aligned relationships data is, in our reading,
overclaiming.

## 5. Production surface

The repository deploys to Fly.io as a FastAPI service
(`netpulse-pauti.fly.dev`) that exposes:

- `POST /detect/bgp` — run all detectors over a configurable window of
  the bound store, return alerts as JSON.
- `GET /alerts` — query persisted alert history (DuckDB-backed) by
  detector, severity, and time window.
- `GET /health` — store path, baseline prefix count, version.
- `GET /metrics` — Prometheus text-format counters (requests by endpoint,
  alerts by detector) and gauges (baseline size).

The production surface is part of the contribution because it forces
the detection logic to be operable: a benchmark that only runs as a
test script does not surface integration cost. The Prometheus surface
is intentionally stdlib-only to keep the deployment image small.

## 6. Related work, with calibration

ARTEMIS [Sermpezis18] is the canonical comparison. It detects more
hijack types (origin Type 0/1, path Type N, squatting), is built around
operator-provided ground truth (ASN/prefix lists, RPKI ROAs), and ships
a real mitigation loop. NetPulse covers a strict subset of detection
shapes; it does not attempt mitigation. The two systems' sub-prefix
detection logic is the same shape, and the YouTube outcome is the same
in both writeups.

PHAS [Lad06] and Pretty Good BGP [Karlin06] are the historical
reference points for, respectively, alert-on-origin-change and the
latency-vs-accuracy framing this paper inherits.

Cloudflare Radar, bgp.tools, and RIPEstat are inspection tools, not
detectors in the streaming sense; they are cited as *sources of
labeled incidents*, not as comparison points.

A head-to-head benchmark across these tools on a shared incident
corpus would be a paper of its own — see §8.

## 7. Honest limitations

1. **One labeled hijack hour for the FPR survey.** The five-hour FPR
   table covers the YouTube case only. A broader cross-collector,
   cross-decade FPR study is open work.
2. **Bounded baseline scope.** `yt_rib_filtered.duckdb` is the real
   RIB at 2008-02-24T16:00Z, but only for `208.65.0.0/16`. The full
   RIB would be ~270k prefixes at 2008 volumes; the filtered pull is
   sufficient for the question asked but a production deployment would
   not filter this way.
3. **CAIDA snapshot temporal drift.** Generic leak detection requires
   the snapshot to be time-aligned with the incident, which the
   benchmark documents per-incident via the optional `asrel_path`
   field. We do *not* claim leak detection works against arbitrary
   historical incidents without an aligned snapshot.
4. **RIS visibility gap.** Not every documented hijack reaches RIS.
   The Cloudflare 2024 case was investigated and excluded from the
   labeled corpus because it never appeared at any RIS collector
   we checked.
5. **No DNS signal yet.** The fusion framing currently uses two
   signals (BGP and Atlas); the planned DNS axis (reachability checks
   from Atlas DNS measurements) is unimplemented.

## 8. Future work

In rough priority order:

1. **DNS as a third fusion axis.** Atlas DNS measurements give a third
   independent signal that should co-fire on outages but not on pure
   route hijacks (which mostly preserve DNS reachability).
2. **Historical CAIDA loader.** A small ingestor that pulls a specific
   `serial-2` snapshot by date would let us populate `asrel_path` for
   each historical incident automatically and close the Google 2017
   GAP.
3. **Cross-collector evaluation at scale.** The mechanism exists
   (`MultiStoreBGPView`); systematic per-incident multi-collector
   replays are the open work.
4. **Side-by-side benchmark with ARTEMIS.** Same corpus, same
   baselines, both tools' alerts published in a single table. This is
   the missing reproducible head-to-head in the literature and is the
   natural next paper.
5. **Mitigation-loop wiring (out-of-scope advisory).** If NetPulse ever
   moves from detection to mitigation it should integrate RPKI ROA
   filtering rather than reinventing the loop; this is documented as
   non-goal in the current spec.

## 9. Reproduction

All numbers in this paper come from one of these commands:

```sh
uv sync && uv run netpulse demo

uv run netpulse ingest bgp --collector rrc00 \
    --start 2008-02-24T18:00:00 --duration 1h \
    --out data/youtube_2008.duckdb

uv run netpulse benchmark replay \
    --incidents data/incidents \
    --baseline data/baselines/yt_rib_filtered.duckdb --chunk 1m

uv run netpulse benchmark stream-latency \
    --incidents data/incidents \
    --baseline data/baselines/yt_rib_filtered.duckdb

uv run python scripts/run_corpus_benchmark.py
uv run python scripts/run_fpr_analysis.py
uv run python scripts/fusion_demo.py
```

See `BENCHMARK.md` for the full reproduction recipe with timing.

## References

The full bibliography lives at `docs/references.md`. The short list:

- Lad et al., *PHAS: A Prefix Hijack Alert System*, USENIX Security 2006.
- Karlin, Forrest, Rexford, *Pretty Good BGP*, IEEE Network 2006.
- Ballani, Francis, Zhang, *A Study of Prefix Hijacking and Interception
  in the Internet*, SIGCOMM 2007.
- Sermpezis et al., *ARTEMIS: Neutralizing BGP Hijacking Within a
  Minute*, IEEE/ACM ToN 2018.
- RFC 4271 — BGP-4; RFC 6480 — RPKI; RFC 6811 — Origin Validation;
  RFC 7908 — Route Leaks.
