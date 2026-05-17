# Changelog

All notable changes to this project are documented here.

The project follows pre-1.0 versioning: breaking changes are allowed in
0.x releases. Once the labeled-incident corpus is at N≥10 and the live
deployment has soaked, an initial 1.0 will lock the schema.

## [unreleased]

### Added (since 0.0.1)
- **Persistent alert history.** `AlertHistoryStore` (DuckDB-backed) and
  `HistoryRecorder` (publisher wrapper) record every emitted alert.
  `netpulse stream --history <path>` and `netpulse serve --history
  <path>` enable the new `GET /alerts` endpoint with time-range,
  detector, and severity filters.
- **Public deployment.** Dockerfile + fly.toml ship the FastAPI surface;
  the project is live at <https://netpulse-pauti.fly.dev/>.
- **Customer-cone-aware route-leak detector** (`customer_cone_leak`).
  Walks each path against transitive customer cones derived by BFS
  over the CAIDA p2c edges; fires on any path that is not
  cone-monotone. Closes the previously open Google 2017 leak GAP —
  corpus is now **4 / 4 with 0 GAP**. `netpulse detect leak --mode
  valley|cone|both`.
- **DNS reachability signal** (`dns_failure_rate`). Active probe loop
  via `dnspython.Resolver`; per-hostname failure-rate detector;
  optional third axis on `MultiSignalCorrelator`. `netpulse ingest
  dns` + `netpulse detect dns`.
- **Cross-collector aggregation.** `MultiStoreBGPView` ATTACHes N BGP
  DuckDB stores read-only and exposes a UNION ALL `bgp_records` view.
  `netpulse detect bgp --in a.db --in b.db ...` consumes it without
  inflating MOAS counts.
- **Per-record streaming-mode latency benchmark.**
  `netpulse benchmark stream-latency` walks records in time order and
  reports microsecond-resolution latency from documented onset to the
  first qualifying detector evaluation. 0 µs on both labeled
  sub-prefix incidents.
- **Corpus benchmark runner.** `scripts/run_corpus_benchmark.py`
  scores every labeled incident as TP / FN / GAP, renders the
  per-incident matrix to `docs/img/corpus_matrix.svg`.
- **Prometheus metrics endpoint.** Stdlib-only `MetricsRegistry`
  exposes `netpulse_requests_total{detector=...}`,
  `netpulse_alerts_total{detector=...}`, and
  `netpulse_baseline_prefixes` on `GET /metrics`. Ready-to-import
  Grafana 10+ dashboard at `docs/grafana/netpulse-dashboard.json`.
- **Per-incident `asrel_path`** in the incident JSON schema so each
  labeled leak gets its own time-aligned CAIDA snapshot.
- **`docs/paper.md`** — paper-style working note (abstract → future
  work) keeping every claim in lockstep with a re-runnable command.
- **`docs/distribution/`** — Show HN drafts, tweet thread, slide-deck
  outline with anticipated Q&A.
- **End-to-end terminal-tour GIF** (`docs/img/tour.gif`) recorded via
  vhs: demo → corpus → streaming-mode → live-API call.
- **`docs/CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`** OSS hygiene.

### Changed
- Performance: RPKI validate(prefix, asn) now uses longest-prefix-
  match against a single canonical-network dict (~43 µs / call against
  859k VRPs, ~23k validations / sec). Previously was a linear scan
  over covering networks (~22 ms / call, **500× slower**).
  Correctness preserved end-to-end (RFC 6811 §2 Cover/Match).
- `SubPrefixHijackDetector` now also flags exact-prefix mismatches
  where the prefix itself is in the baseline but the origin differs.

### Fixed
- Default route (`0.0.0.0/0`) appearing in some RIB dumps was being
  treated as a covering supernet by `BGPBaseline`, producing a spurious
  sub-prefix alert on every non-baseline /24. Now filtered at load time.

## 0.0.1

Initial public release. Phases 0-5 of the roadmap in `CLAUDE.md` are
working end-to-end.

### Detectors
- `moas` — same-prefix multi-origin AS.
- `subprefix_hijack` — RFC 6811-style supernet check against a RIB-
  derived baseline.
- `withdraw_spike` — many prefixes go silent without re-announcement.
- `rpki_invalid` — RFC 6811 Origin Validation against Cloudflare's
  published rpki.json.
- `route_leak` — RFC 7908 valley-free path inference against CAIDA
  serial-2 inferred AS relationships.
- `atlas_loss_spike` — global packet-loss spike across RIPE Atlas
  ping probes.
- `multi_signal_fusion` — correlator that emits one critical alert
  when BGP detectors fire alongside an Atlas RTT anomaly in the same
  window.

### Surfaces
- `netpulse demo` — bundled real-data fixture, no setup, ~1 second.
- `netpulse ingest {bgp,atlas,rpki,asrel}` — typed pulls with native
  bulk loaders for RPKI (859k VRPs in ~20 s) and CAIDA (~739k
  relationships in ~7 s).
- `netpulse detect {bgp,atlas,leak,rpki}` — per-window detector runs.
- `netpulse benchmark replay` — replays labeled incidents with
  per-incident `bgp_store_path` + `baseline_path` resolved from the
  fixture JSON.
- `netpulse stream` — RIS Live WebSocket → rolling window → detectors,
  with cooldown-based dedup.
- `netpulse serve` — FastAPI app: `GET /health`, `POST /detect/bgp`,
  `GET /alerts`.

### Labeled incidents (N=3)
- 2008-02-24 YouTube / Pakistan (sub-prefix hijack)
- 2018-04-24 MyEtherWallet / Amazon Route 53 (sub-prefix hijack)
- 2018-11-12 MainOne → Google (RFC 7908 Type-1 leak)

### Engineering
- Python 3.11+ via uv, mypy strict, ruff, GitHub Actions CI matrix
  (Python 3.11+3.12 × Ubuntu+macOS).
- DuckDB single-file storage for every signal; native bulk loaders for
  large feeds.
- Multi-stage Dockerfile, Fly.io deployment manifest.
