# Changelog

All notable changes to this project are documented here.

The project follows pre-1.0 versioning: breaking changes are allowed in
0.x releases. Once the labeled-incident corpus is at N≥10 and the live
deployment has soaked, an initial 1.0 will lock the schema.

## [unreleased]

### Added
- **`OriginDeaggregationDetector`** — new detector that fires when a
  single origin AS emits a burst of more-specific (/23+) prefixes
  in the observation window. Catches the Telekom-Malaysia-2015 shape
  (massive self-deaggregation through an upstream) that neither
  `MOASDetector` nor `SubPrefixHijackDetector` reports because every
  announce has a legitimate origin. Shape-only — no baseline needed.
  Default thresholds: ≥200 distinct prefixes from one origin, with
  ≥70% at /23-or-longer. Wired into `netpulse demo` for hijack
  incidents (3 detectors run instead of 2); fires on `indosat_2014`
  in addition to subprefix_hijack. 6 unit tests cover the threshold
  matrix.

## [0.2.0] -- 2026-05-26

### Added
- **Corpus N=4 → N=7.** Three new labeled incidents land in this
  release. `data/incidents/`:
  - `indosat_2014.json` — AS4761 MOAS hijack; 19 subprefix_hijack
    alerts across both detector branches.
  - `vodafone_idea_2024.json` — AS55410 tier-1-to-tier-1 leak
    (Bharti Airtel ↔ Tata Communications); 1,015 customer_cone_leak
    alerts entirely through AS55410.
  - `rostelecom_2017.json` — AS12389 briefly re-announced ~36
    prefixes belonging to Mastercard, Visa, USPS, and other US
    financial networks; 4 subprefix_hijack alerts against a
    hand-curated RIB-verified baseline.
- Corpus benchmark: **7/7 TP / 0 FN / 0 GAP**, 100% detector coverage.

### (carried from 0.2.0 development)
- **Corpus N=5 → N=6.** Vodafone Idea (AS55410) tier-1-to-tier-1 leak
  of 2024-09-30 added to `data/incidents/vodafone_idea_2024.json`.
  Real RIS data: 9,394 paths from rrc00 over a 30-minute window with
  filter `path "_55410_"`, 224 distinct prefixes leaking in the
  `AS9498 → AS55410 → AS45528` direction with a 6× AS55410 path-prepend
  (a botched traffic-engineering attempt). Both detectors fire
  on-target: route_leak = 43, customer_cone_leak = 1,015, all through
  AS55410. CAIDA serial-2 snapshot 20240901 fetched into
  `data/caida_asrel_2024_09.duckdb`. Demo gets a matching
  `_DEMO_STORIES` entry + AS-name annotations (`AS55410 (Vodafone Idea)`,
  `AS9498 (Bharti Airtel)`, `AS45528 (Tata Communications)`).
- Corpus benchmark roll-up regenerated: **6/6 TP / 0 FN / 0 GAP**,
  100% detector-coverage rate. `docs/img/corpus_matrix.svg` re-rendered.

### Fixed
- **`scripts/run_corpus_benchmark.py`** had a sign bug in `other_alerts`
  for leak incidents: when one detector fired more on-target alerts
  than the other, the runner mixed `len(valley_alerts)` with the
  cone detector's on-target count, producing negative "other" totals
  (Vodafone first reported `other=-972`). Fixed by routing
  `total_alerts`, `total_on_target`, and `catching` through the same
  detector branch.

### (other Added — pre-existing this release)
- **`netpulse demo --live N`** taps RIPE RIS Live for N seconds (1-600)
  and pipes every update through MOAS in real time. A rich.Live
  panel updates 4×/sec with rolling counters: updates, prefixes,
  distinct peers, collectors observed, and MOAS alerts emitted.
  Border flips green→red the moment the first alert fires. Final
  summary table prints duration / rate / per-collector stats.
  Verified live: 8,471 updates / 8 s = ~1,054/s across 23
  collectors and 160 peers on a fresh tap.
- **Startup Panel for `netpulse stream`** matching the demo style:
  the connection params, baseline size, and history path are
  shown up-front so the operator knows what they're tapping.

## [0.1.0] — 2026-05-25

First versioned release. Detector roster + 5-incident corpus + live
deployment + Streamlit dashboard + observability + ARTEMIS-comparison
scaffolding all stable. Schema considered locked for the 0.1 series;
breaking changes will bump 0.2 / 1.0 as the corpus grows toward N=10.

### Changed
- **`netpulse demo` round-3 polish:**
  - **`--incident all`** plays all 5 corpus incidents back-to-back
    with a horizontal rule between each and a final Rich roll-up
    table summarizing verdict, alerts fired per detector, wall time,
    and stream-latency per incident.
  - **Friendly AS names** in the hijacker path panel: the attacker
    AS now reads as `AS4761 (PT Indosat)` etc. — ~30 ASes
    curated in `_AS_NAMES`. Other hops stay numeric to keep the
    line scannable.
  - **Stream-latency from documented onset** added to the verdict
    Panel for hijack incidents. Runs `replay_subprefix_streaming`
    after the batch detection and reports the microsecond delta
    (e.g. `0µs from onset` on YouTube and MyEtherWallet).
- **`netpulse demo` is now a 10/10 instrument-grade demo.**
  Curated narrative + automatic-detector-routing for all 5 corpus
  incidents (3 hijacks + 2 leaks):
  - Story Panel for each incident with the human background,
    victim/attacker callout, and ISO timestamps.
  - **Hijacker AS-path panel** pulled from the actual BGP store
    -- shows the recorded path (e.g. `AS3333 → AS12859 → AS6461
    → AS3491 → AS17557 ←ORIGIN`) with the attacker AS highlighted.
  - **Auto-dispatch** by incident_type: hijack incidents run
    `MOASDetector + SubPrefixHijackDetector`; leak incidents
    automatically load the matching CAIDA AS-relationships
    snapshot and run `RouteLeakDetector + CustomerConeLeakDetector`.
  - **Noise filtering**: by default MOAS warnings on prefixes
    unrelated to the labeled incident are folded into a single
    summary row, and the alert table is capped at 8 rows with a
    "+N more" footer. `--all` shows everything.
  - **Color-coded verdict** Panel: red `✗ HIJACK DETECTED` for
    hijacks, red `✗ LEAK DETECTED` for leaks, yellow
    `⚠ Warnings only`, green `✓ Clean window`.
  - **`--list` flag** renders a Rich Table of the 5 curated
    incidents with availability indicators (`bundled` vs
    `fetch first`).
  - Reproduce-live curl hint at the bottom for the YouTube case;
    consistent next-step pointers for the others.
  - `docs/tapes/demo.tape` + `docs/tapes/tour.tape` rewritten
    around the new flow; `docs/img/demo.gif` (498KB) and
    `docs/img/tour.gif` (773KB) re-rendered via vhs.

### Added (since 0.0.1)
- **ARTEMIS head-to-head scaffolding.**
  `scripts/artemis_export_config.py` converts any NetPulse labeled
  incident JSON + baseline DuckDB into an ARTEMIS-shaped YAML rule
  config (`prefixes:` + `asns:` + `rules:` with YAML anchors).
  `scripts/artemis_compare.py` reads NetPulse's
  `docs/corpus_benchmark.json` plus ARTEMIS hijack dumps and emits a
  per-incident head-to-head row (NetPulse outcome + alert count vs
  ARTEMIS fired + alert count + native hijack-type label). The full
  methodology + ARTEMIS docker-compose recipe lives in
  `docs/artemis-comparison-plan.md`. Six new tests on the exporter +
  comparison runner.
- **Corpus-expansion playbook** at `docs/corpus-expansion-playbook.md`
  captures everything learned moving the corpus from N=4 to N=5:
  the filter-quoting trap (`path "_4761$"` not `path '_4761$'`),
  RIS collector geography (which collector saw which incident),
  the /24 prefix-length filter that hides /32-grain hijacks like
  Cloudflare 2024, and the hijack-vs-deaggregation-leak distinction
  that knocked Telekom Malaysia 2015 out of corpus consideration.
- **Indosat 2014 MOAS hijack** added to the labeled-incident corpus.
  AS4761 re-announced ~3,700 prefixes outside its 114.4.0.0/15
  allocation around 18:25 UTC on 2014-04-02 (51,203 RRC00 records
  fetched via `path "_4761$"`). Baseline carries five
  AS45305/AS45454/AS45348 supernets verified against the RRC00 RIB
  90 minutes pre-hijack. `SubPrefixHijackDetector` fires **19
  alerts** -- 3 exact-prefix shape + 16 sub-prefix shape -- so the
  incident exercises both detector branches. **Corpus now N=5,
  TP=5, FN=0, GAP=0.**
- **Streamlit alert console.** `netpulse dashboard --history alerts.duckdb`
  launches a web UI over the alert-history DuckDB: alerts-over-time
  bar chart with adjustable bucketing, by-detector and by-severity
  breakdowns, top-entities table, sidebar filters (date range,
  detector substring, severity). Pure-Python data layer (`netpulse.
  dashboard.data`) is unit-testable without a Streamlit runtime;
  Streamlit itself is an optional `dashboard` extra so the core
  install stays lean. 8 new tests covering bucketize edge cases and
  summarize_window sort order.
- **Structured JSON logging + request middleware.** New
  `netpulse.observability` exposes `configure_logging(json_mode=...)`
  and `RequestLoggingMiddleware`. Every HTTP request now logs with a
  stable `x-request-id` (echoed back to the client), method, path,
  status, and duration_ms. `netpulse serve --log-format json|text`
  toggles structured vs human-readable output.
- **Per-endpoint request-duration histogram** in the metrics surface.
  `netpulse_request_duration_seconds` with default buckets at 1 ms →
  10 s lets an operator graph p50/p95/p99 latency per endpoint via
  Prometheus' `histogram_quantile`.
- **`GET /ready`** liveness/readiness split. `/health` returns 200 as
  long as the process is alive; `/ready` opens the BGP DuckDB store
  and returns 503 if it can't query a count. Fly.io's `fly.toml` now
  has two HTTP checks so a corrupt fixture routes traffic away from
  the machine without restart-looping.
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

Initial public release. Phases 0-5 of the roadmap in `PROJECT.md` are
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
- 2008-02-24 YouTube /24 (sub-prefix hijack)
- 2018-04-24 MyEtherWallet / Amazon Route 53 (sub-prefix hijack)
- 2018-11-12 MainOne → Google (RFC 7908 Type-1 leak)

### Engineering
- Python 3.11+ via uv, mypy strict, ruff, GitHub Actions CI matrix
  (Python 3.11+3.12 × Ubuntu+macOS).
- DuckDB single-file storage for every signal; native bulk loaders for
  large feeds.
- Multi-stage Dockerfile, Fly.io deployment manifest.
