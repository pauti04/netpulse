"""Build the ML feature table from unfiltered incident BGP windows.

Reads the two unfiltered windows fetched into ``data/ml/`` (see the
ingest commands in ``docs/ml/README.md``), aggregates per (prefix,
origin) observation, and writes a compact parquet feature table —
committed so the eval reproduces without a multi-minute BGP pull.

Label (``is_culprit``) = the observation's origin is the incident's
documented culprit AS. The label is used only for *evaluation* of the
unsupervised scorer, never for training.

    uv run --extra ml python scripts/build_ml_dataset.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from netpulse.ml.anomaly import ObservationRow, extract_features

REPO = Path(__file__).resolve().parent.parent
ML = REPO / "data" / "ml"

# (incident id, unfiltered window store, documented culprit AS)
WINDOWS = [
    ("indosat_2014", ML / "indosat_2014_unfiltered.duckdb", 4761),
    ("rostelecom_2017", ML / "rostelecom_2017_unfiltered.duckdb", 12389),
]

_AGG_SQL = """
SELECT prefix, origin_as,
       COUNT(DISTINCT peer_as) AS n_peers,
       COUNT(DISTINCT as_path) AS n_paths,
       AVG(LENGTH(as_path) - LENGTH(REPLACE(as_path, ' ', '')) + 1) AS mean_plen,
       MIN(LENGTH(as_path) - LENGTH(REPLACE(as_path, ' ', '')) + 1) AS min_plen
FROM bgp_records
WHERE update_type = 'A' AND origin_as IS NOT NULL
GROUP BY prefix, origin_as
"""


def main() -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    all_keys: list[str] = []
    all_rows: list[list[float]] = []
    all_labels: list[int] = []
    all_incidents: list[str] = []

    for incident, store, culprit in WINDOWS:
        if not store.exists():
            raise SystemExit(f"missing {store} — fetch it first (see docs/ml/README.md)")
        con = duckdb.connect(str(store), read_only=True)
        rows = [
            ObservationRow(
                prefix=str(p),
                origin_as=int(o),
                n_peers=int(npe),
                n_paths=int(npath),
                mean_path_len=float(mpl or 0.0),
                min_path_len=float(minpl or 0.0),
            )
            for p, o, npe, npath, mpl, minpl in con.execute(_AGG_SQL).fetchall()
        ]
        matrix, keys = extract_features(rows)
        all_rows.extend(matrix)
        all_keys.extend(keys)
        all_labels.extend(1 if r.origin_as == culprit else 0 for r in rows)
        all_incidents.extend(incident for _ in rows)
        n_pos = sum(1 for r in rows if r.origin_as == culprit)
        print(f"{incident}: {len(rows)} observations, {n_pos} culprit-origin positives")

    cols = list(zip(*all_rows, strict=True)) if all_rows else [[] for _ in range(8)]
    from netpulse.ml.anomaly import FEATURE_NAMES

    table = pa.table(
        {
            "incident": all_incidents,
            "key": all_keys,
            **{name: list(cols[i]) for i, name in enumerate(FEATURE_NAMES)},
            "is_culprit": all_labels,
        }
    )
    out = ML / "hijack_features.parquet"
    pq.write_table(table, out)
    print(f"wrote {table.num_rows} rows × {table.num_columns} cols -> {out}")


if __name__ == "__main__":
    main()
