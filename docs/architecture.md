# Architecture

## Data flow

```
ingest -> storage -> features -> detectors -> alerts -> (publishers | api | dashboard)
```

Each stage is a thin module with no upstream knowledge of consumers. Records
flow through DuckDB rather than in-memory queues so any stage can be replayed
independently — this is what makes the historical benchmark reproducible.

## Modules

- `ingest/`: pulls raw data from external sources (RIPE RIS via `pybgpstream`,
  RIPE Atlas via `cousteau`/`sagan`, DNS via `dnspython`) and normalizes into
  typed records.
- `storage/`: DuckDB single-file store. Schemas live in `schema.py`; read/write
  helpers in `duckdb_store.py`. One file per stream so backfills do not
  contend.
- `features/`: per-signal feature extraction over rolling time windows. Stateless
  functions over a `FeatureWindow` view of the store.
- `detectors/`: per-signal detectors and the multi-signal fusion layer. Each
  detector implements the `DetectorBase` ABC with
  `score(features: FeatureWindow) -> list[Alert]`.
- `alerts/`: the `Alert` dataclass and publishers (stdout, webhook, slack).
- `benchmark/`: historical replay harness, metrics (precision/recall/latency),
  leaderboard generator.
- `api/`: FastAPI app exposing alerts and dashboard data.
- `cli.py`: Typer entry point with `ingest`, `detect`, `benchmark`, `serve`.

## Conventions

- Timestamps: `int` microseconds since Unix epoch, UTC. Convert only at module
  boundaries (CLI input, API output, external library calls).
- Internal types: dataclasses. Pydantic only at API/CLI boundaries.
- One public class or function per file when nontrivial.

Per-module detail is added as each phase lands.
