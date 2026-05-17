# NetPulse — slide-deck outline

A 12-slide deck for a 15-minute talk (meetup, internal demo, thesis
defense framing). One title per slide, two bullets max, one chart or
code snippet where called out. The deck is meant to be cut, not
expanded — the writeup at `docs/paper.md` is the long form.

## 1. Title

**NetPulse: an open, reproducible benchmark for BGP anomaly detection**

- Sub: 4 incidents · 4 TP / 0 GAP / 0 FN · 0 µs streaming latency
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
- 4 TP: YouTube 2008, MyEtherWallet 2018, MainOne 2018, Google 2017.
- The Google 2017 case was a GAP under the bilateral valley-free
  check (CAIDA 2017-08 has the AS15169↔AS4713 pair as `unknown`);
  caught by the customer-cone-aware variant — see slide 9.
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

## 9. Why valley-free vs. cone matters (Google 2017)

- Path: `3333 1103 286 701 15169 4713`.
- Pair directions vs CAIDA 2017-08:
  `[c2p, c2p, c2p, p2c, unknown]` → valley-free abstains.
- Customer cones vs same data:
  - cone(701) has 34,619 ASes, includes 15169 → step 4 downhill.
  - cone(15169) has 10 ASes, excludes 4713 → step 5 uphill.
- Downhill-then-uphill ⇒ alert. **123,749** alerts on the documented
  leak window. The corpus has 0 GAP today as a result.

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

- DNS as the third fusion axis (Atlas DNS measurements).
- Customer-cone provenance audit (print the actual customer chain
  that motivates a cone-monotone violation).
- Side-by-side benchmark with ARTEMIS on the same corpus.
- Same numbers. Same baselines. Same table.

## Closing slide

- GitHub: github.com/pauti04/netpulse
- Live: netpulse-pauti.fly.dev
- Paper: docs/paper.md
- MIT · Python 3.11 · DuckDB · libBGPStream · RIPE Atlas

---

### Speaker notes — anticipated Q&A

**Q: Why three buckets (TP / FN / GAP) when the current corpus has
no GAP?**
A: The bucket exists because not every miss is the same kind of
miss. A future incident could land in GAP if it depends on a data
source we can't recover (e.g. a hijack that never reached any public
collector — see the 2024 Cloudflare case explicitly excluded from the
labeled corpus for that reason). Keeping GAP separate from FN lets
the corpus distinguish "the algorithm missed" from "no detector with
this input class could possibly catch this". The Google 2017 case
*was* a GAP under valley-free; it became a TP under the cone variant.

**Q: Why ship both leak detectors instead of merging them?**
A: Different evidence shapes. Valley-free's evidence is a per-pair
direction sequence the operator can trace pair-by-pair against a
CAIDA dump. The cone variant's evidence is "is this AS in that AS's
transitive customer cone" — a different audit trail, also worth
having. Collapsing into one would hide which mode produced the
alert.

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
