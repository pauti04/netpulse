# NetPulse — slide-deck outline

A 12-slide deck for a 15-minute talk (meetup, internal demo, thesis
defense framing). One title per slide, two bullets max, one chart or
code snippet where called out. The deck is meant to be cut, not
expanded — the writeup at `docs/paper.md` is the long form.

## 1. Title

**NetPulse: an open, reproducible benchmark for BGP anomaly detection**

- Sub: 4 incidents · 3 TP / 1 GAP / 0 FN · 0 µs streaming latency
- Sub: https://github.com/pauti04/netpulse

## 2. The problem

- BGP-anomaly-detection literature is rich; reproducible benchmarks
  on labeled real-world incidents are thin.
- "Detection latency was under 60 s on case X" doesn't tell you what
  the same algorithm would do on case Y, or on quiet hours either side.

## 3. The thesis

- The contribution isn't a new algorithm. It's an *open, end-to-end
  implementation* of standard detectors plus a *re-runnable benchmark
  on labeled historical incidents* with a transparent methodology.
- Read it. Re-run it. Argue with it.

## 4. Architecture

`ingest → storage → features → detectors → alerts → (publishers | api | benchmark)`

(Reference: the mermaid diagram in README.md, top of the file.)

- Each stage talks through DuckDB, not in-memory queues — every stage
  is independently replayable.
- 5 detectors: MOAS, sub-prefix, withdraw-spike, RFC 6811 RPKI,
  RFC 7908 route-leak. Plus Atlas loss spike.

## 5. The corpus (show `docs/img/corpus_matrix.svg`)

- 4 labeled incidents from primary sources.
- 3 TP (YouTube 2008, MyEtherWallet 2018, MainOne 2018).
- 1 GAP (Google 2017 — CAIDA snapshot missing AS pair; detector
  abstains).
- No FN. No fabricated incidents.

## 6. Latency, honest version

- *Chunk-bounded* — replay harness, expanding window. 3.0 s on
  YouTube at `--chunk 1m`. Bounded by the chunk size, not the
  detector.
- *Streaming-mode* — per-record evaluation. **0 µs from documented
  onset** on both sub-prefix incidents.

## 7. False-positive survey (show `docs/img/fpr_per_hour.svg`)

- 4 background hours + 1 hijack hour, real RRC00 data, 13,961 distinct
  prefixes.
- Sub-prefix detector: 1 alert total, in the hijack hour.
- MOAS row published too — that's the empirical case for needing the
  supernet-aware detector.

## 8. Multi-signal fusion on real data

- 2018-11-12 MainOne → Google leak.
- BGP route-leak: 1,985 alerts on the AS37282→AS15169 path shape.
- Atlas: median RTT to 8.8.8.8 jumps 1.31× above baseline (38.0 → 49.9 ms).
- Correlator → 1 fused critical alert. `scripts/fusion_demo.py`.

## 9. Why CAIDA time-alignment matters

- Same MainOne archive, two CAIDA snapshots:
  - 2018-11 snapshot: 1,985 MainOne-shape alerts.
  - Current snapshot: 0 MainOne-shape alerts.
- Difference is temporal drift in the inferred relationships, not the
  algorithm.
- This is why the corpus has a `GAP` bucket: missing input ≠ failure.

## 10. Production surface (show curl + json)

- FastAPI on Fly.io: https://netpulse-pauti.fly.dev/health
- `POST /detect/bgp`, `GET /alerts`, `GET /metrics` (Prometheus
  text-format).
- Cross-collector aggregation: `--in` repeatable on `detect bgp`,
  DuckDB ATTACH + UNION ALL view.

## 11. Honest limitations

- 1 hijack hour in the FPR survey.
- Bounded baseline scope (filtered to /16) — full-RIB pull is now
  feasible with libBGPStream filters.
- No DNS axis yet. CAIDA historical loader still manual.
- 2024 Cloudflare event excluded — never reached any RIS collector
  we checked.

## 12. Roadmap

- Time-aligned CAIDA loader (closes the Google 2017 GAP).
- DNS as the third fusion axis (Atlas DNS measurements).
- Side-by-side benchmark with ARTEMIS on the same corpus.
- Same numbers. Same baselines. Same table.

## Closing slide

- GitHub: github.com/pauti04/netpulse
- Live: netpulse-pauti.fly.dev
- Paper: docs/paper.md
- MIT · Python 3.11 · DuckDB · libBGPStream · RIPE Atlas

---

### Speaker notes — anticipated Q&A

**Q: Why call it `GAP` instead of `FN`?**
A: An FN credits the algorithm with a miss it didn't make. The Google
2017 detector code is the same code that fires on MainOne 2018. What
differs is a single relationship in the CAIDA snapshot. Folding that
into FN overclaims the failure as algorithmic and lets the actual
issue (snapshot temporal drift) hide.

**Q: Why DuckDB, not Postgres / Parquet / ClickHouse?**
A: Single-file, embedded, no server, native ATTACH for cross-store
UNION views, microsecond random access on the 50k-announce/h scale
this benchmark works at. The benchmark needs to be re-runnable in 5
minutes by a reader — Postgres adds setup, Parquet without an engine
adds query complexity. ClickHouse would work but isn't worth the
weight at this data size.

**Q: How does this compare to ARTEMIS?**
A: ARTEMIS detects more hijack shapes (path Type-N, squatting) and
has an actual mitigation loop. NetPulse covers a subset of detection
shapes and no mitigation. The sub-prefix logic is the same shape in
both; the contribution claim is the open benchmark, not the algorithm.
The natural next paper is a side-by-side run.

**Q: How much of this is AI-generated?**
A: The code is human-driven design with AI-assisted writing. Hard
rules in the repo: no fabricated incident data; no invented external
API shapes; no over-engineering. Every number in the writeup is from
a command in the repo, not from a model.
