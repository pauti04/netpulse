# NetPulse — Project context

Living context document. Mission, target architecture, tech-stack
choices, conventions, and roadmap. Updated when the project shape
changes.

## Mission

Detect Internet outages, BGP hijacks, route leaks, and reachability
degradations in real time by fusing three signals: BGP routing data
(RIPE RIS), RIPE Atlas active probes, and DNS reachability. Validate
via a curated public benchmark of historical incidents.

## Why it exists

Commercial tools (Cloudflare Radar, ThousandEyes, Catchpoint, Kentik)
solve this but are closed-source. Academic tools exist but are not
production-grade. The differentiator is **honest evaluation**: a
reproducible benchmark of detection latency and precision/recall
against labeled historical incidents, which no existing tool
publishes openly. When making design tradeoffs, prefer the option
that produces clearer benchmark numbers.

## Target architecture

```
src/netpulse/
├── ingest/        # pulls from BGP, Atlas, DNS -> normalized records
├── storage/       # DuckDB single-file; schemas + read/write helpers
├── features/      # per-signal feature extraction over rolling windows
├── detectors/     # per-signal detectors + multi-signal fusion
├── alerts/        # Alert dataclass + publishers (stdout, webhook, slack)
├── benchmark/     # historical replay harness + metrics + leaderboard
├── api/           # FastAPI for serving alerts and dashboards
└── cli.py         # Typer-based CLI; main entry point
```

Data flow: `ingest -> storage -> features -> detectors -> alerts -> (publishers | api | dashboard)`.

## Tech stack — fixed choices

- Python 3.11+, managed by **uv** (not pip, not poetry)
- Lint/format: ruff (configured strict)
- Types: mypy `strict` on `src/`, lenient on `tests/` and `scripts/`
- Tests: pytest, with `pytest-asyncio` for async paths
- Storage: DuckDB (single-file, embedded), no Postgres or SQLite
- BGP: `pybgpstream` (libBGPStream wrapper)
- Atlas: `ripe.atlas.cousteau` and `ripe.atlas.sagan`
- DNS: `dnspython`
- API: FastAPI + uvicorn
- CLI: Typer + Rich for output
- Dashboard (later): Streamlit
- Deploy: Fly.io (live at <https://netpulse-pauti.fly.dev/>)
- License: MIT
- CI: GitHub Actions running ruff + mypy + pytest on push to main

## Code conventions

- All timestamps stored as `int` microseconds since Unix epoch, UTC.
  Convert at boundaries only.
- Detectors implement an ABC `DetectorBase` with
  `score(features: FeatureWindow) -> list[Alert]`.
- Use dataclasses (not Pydantic) for internal types; Pydantic only
  at API/CLI boundaries.
- One public class or function per file when nontrivial; small
  helpers can group.
- Every new module gets at least one test before it is considered
  done.
- No emojis in code, logs, or commit messages. Plain prose.
- Docstrings: short, factual, describe what not why (the "why" goes
  in `PROJECT.md` or `docs/`).

## Hard rules — do NOT do these

1. **Do not fabricate BGP incident data.** Incidents are populated
   only from primary sources (RIPE NCC, Cloudflare, BGPmon, ISC).
   Schemas and well-documented public examples are fine; invented
   timestamps, AS numbers, or details are not.
2. **Do not invent API response shapes.** Code against real
   responses; if a library's output schema is unknown, capture a
   real response first.
3. **Do not over-engineer.** No metaclasses, no plugin systems, no
   premature abstraction. The fusion layer needs polymorphism; most
   things are plain functions and dataclasses.
4. **Do not silently install or pin major-version dependencies**
   without flagging. If a library is unmaintained or has multiple
   incompatible major versions, raise it.
5. **No AI-generated incident lists, dummy data that looks real, or
   "example" hijacks beyond the well-documented public ones.**
   Better to have empty fixtures than fake-looking ones.

## Status

- [x] Phase 0: Setup
- [x] Phase 1: BGP ingestion — `netpulse ingest bgp` pulls from RIPE
      RIS via `pybgpstream`; `features.bgp` aggregates per-prefix
      origins and announce/withdraw counts.
- [x] Phase 2: BGP detectors — `MOASDetector`,
      `SubPrefixHijackDetector`, `WithdrawSpikeDetector` wired
      through `netpulse detect bgp`. RPKI and route-leak detectors
      added. Customer-cone-aware leak detector added to close the
      Google 2017 case.
- [x] Phase 3: Replay harness + incident dataset — replay harness
      complete (`netpulse benchmark replay` + per-record
      `stream-latency` mode); 5 labeled incidents in
      `data/incidents/`; corpus runner reports TP / FN / GAP per
      incident. **Current corpus: N=5, TP=5, FN=0, GAP=0.**
- [x] Phase 4: RIPE Atlas integration — `netpulse ingest atlas`
      pulls real probe-level ping measurements via cousteau / sagan
      against a verified live response shape.
- [x] Phase 5: Multi-signal fusion — `MultiSignalCorrelator` fuses
      BGP alerts with Atlas RTT jumps; optional third axis for DNS
      failures.
- [x] Phase 6: DNS signal — `netpulse ingest dns` (active probes via
      `dnspython`) + `DNSFailureRateDetector` + DNS axis on the
      correlator.
- [x] Phase 7: Dashboard — Grafana 10+ dashboard JSON ships at
      `docs/grafana/netpulse-dashboard.json`. Richer surface lands
      via `netpulse dashboard --history <path>`: a Streamlit
      alert-console over the AlertHistoryStore with adjustable
      bucketing, by-detector / by-severity breakdowns, and a raw
      alerts table. Pure-Python data layer is unit-testable.
- [~] Phase 8: Full benchmark — methodology, FPR survey, latency
      characterization, and per-incident matrix all complete. Open:
      more labeled incidents from primary sources; cross-collector
      evaluation at scale; head-to-head with ARTEMIS.
- [x] Phase 9: Writeup + deploy — Fly.io deployment live;
      `docs/paper.md` is the paper-style writeup; distribution
      materials in `docs/distribution/`.
