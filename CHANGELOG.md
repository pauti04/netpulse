# Changelog

All notable changes to this project are documented here.

The project follows pre-1.0 versioning: breaking changes are allowed in
0.x releases. Once the labeled-incident corpus is at N≥10 and the live
deployment has soaked, an initial 1.0 will lock the schema.

## [unreleased]

### Added
- **Persistent alert history.** `AlertHistoryStore` (DuckDB-backed) and
  `HistoryRecorder` (publisher wrapper) record every emitted alert.
  `netpulse stream --history <path>` and `netpulse serve --history
  <path>` enable the new `GET /alerts` endpoint with time-range,
  detector, and severity filters.
- **Public deployment.** Dockerfile + fly.toml ship the FastAPI surface;
  the project is live at <https://netpulse-pauti.fly.dev/>.
- **`docs/CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`** OSS hygiene.

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
