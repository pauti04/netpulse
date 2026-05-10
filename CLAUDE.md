# NetPulse — Project context for Claude

This file is auto-loaded by Claude Code in this repo. Keep it current.

## Mission

Detect Internet outages, BGP hijacks, route leaks, and reachability degradations
in real time by fusing three signals: BGP routing data (RIPE RIS), RIPE Atlas
active probes, and DNS reachability. Validate via a curated public benchmark of
historical incidents.

## Why it exists

Commercial tools (Cloudflare Radar, ThousandEyes, Catchpoint, Kentik) solve this
but are closed-source. Academic tools exist but are not production-grade. The
differentiator is **honest evaluation**: a reproducible benchmark of detection
latency and precision/recall against labeled historical incidents, which no
existing tool publishes openly. When making design tradeoffs, prefer the option
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

## Tech stack — fixed choices, do not propose alternatives

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
- Deploy (later): Fly.io
- License: MIT
- CI: GitHub Actions running ruff + mypy + pytest on push to main

## Code conventions

- All timestamps stored as `int` microseconds since Unix epoch, UTC. Convert at
  boundaries only.
- Detectors implement an ABC `DetectorBase` with
  `score(features: FeatureWindow) -> list[Alert]`.
- Use dataclasses (not Pydantic) for internal types; Pydantic only at API/CLI
  boundaries.
- One public class or function per file when nontrivial; small helpers can group.
- Every new module gets at least one test before it is considered done.
- No emojis in code, logs, or commit messages. Plain prose.
- Docstrings: short, factual, describe what not why (the "why" goes in CLAUDE.md
  or `docs/`).

## Hard rules — do NOT do these

1. **Do not fabricate BGP incident data.** When the project gets to the benchmark
   phase, the user will populate the incident dataset from primary sources. You
   may generate the schema and a few well-documented public examples (e.g., the
   YouTube/Pakistan 2008 hijack) but never invent timestamps, AS numbers, or
   incident details. If unsure, leave a `# TODO: user to populate` placeholder.
2. **Do not invent API response shapes.** If you do not know what `pybgpstream`
   or the Atlas API actually returns, say so and stop — do not write code
   against an imagined schema. The user will paste real responses.
3. **Do not over-engineer.** No metaclasses, no plugin systems, no premature
   abstraction. The fusion layer will need polymorphism eventually; everything
   else is plain functions and dataclasses.
4. **Do not exceed session scope.** Each session has a defined deliverable. Do
   not start the next phase even if you have time.
5. **Do not silently install or pin major-version dependencies** without
   flagging. If a library is unmaintained or has multiple incompatible major
   versions, raise it.
6. **Do not use AI-generated incident lists, dummy data that looks real, or any
   "example" hijacks beyond the well-documented public ones.** Better to have
   empty fixtures than fake-looking ones.

## Status

- [x] Phase 0: Setup
- [x] Phase 1: BGP ingestion — `netpulse ingest bgp` pulls from RIPE RIS
      via `pybgpstream` into the DuckDB store; `features.bgp` aggregates
      per-prefix origins and announce/withdraw counts over a window.
- [x] Phase 2: BGP detectors — `MOASDetector` flags any multi-origin
      prefix; `SubPrefixHijackDetector` flags a more-specific announced
      from an AS unauthorized for the covering supernet (the actual
      shape of the YouTube hijack). Both wired through `netpulse detect
      bgp`. v2 work: baseline-window suppression of chronic multi-origin
      prefixes in MOAS.
- [~] Phase 3: Replay harness + incident dataset — harness complete
      (`netpulse benchmark replay`, expanding-window latency, summary
      metrics, optional baseline). One labeled incident populated
      (`youtube_pakistan_2008.json`, verified=true with onset_iso pulled
      from the data); remaining ~19 incidents blocked on user research.
      First real benchmark: 1/1 detected, 3.0s latency from onset on
      real RRC00 archive data — see `BENCHMARK.md`.
- [ ] Phase 4: RIPE Atlas integration — _blocked_: cannot write code
      against `ripe.atlas.cousteau` / `ripe.atlas.sagan` response shapes
      without seeing real output (hard rule 2). User to paste a real
      measurement response before this phase can start.
- [ ] Phase 4: RIPE Atlas integration
- [ ] Phase 5: Multi-signal fusion
- [ ] Phase 6: DNS signal
- [ ] Phase 7: Dashboard
- [ ] Phase 8: Full benchmark
- [ ] Phase 9: Writeup + deploy
