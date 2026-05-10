"""DuckDB-backed alert history.

Detectors fire alerts; without storage they are emitted-and-forgotten,
which means there is no answer to "what fired between T1 and T2" the
morning after an incident. This module persists every alert into a
single-file DuckDB so the stream subcommand and the FastAPI surface can
serve historical queries.

The schema is flat -- one row per alert, with the structured ``evidence``
dict stored as a JSON string. Querying by detector, severity, entity, or
time range is straightforward SQL.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import duckdb

from netpulse.alerts import Alert

ALERTS_TABLE = "alerts"


CREATE_ALERTS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {ALERTS_TABLE} (
    timestamp_us     BIGINT NOT NULL,
    detector         VARCHAR NOT NULL,
    severity         VARCHAR NOT NULL,
    entity           VARCHAR NOT NULL,
    summary          VARCHAR NOT NULL,
    window_start_us  BIGINT NOT NULL,
    window_end_us    BIGINT NOT NULL,
    evidence_json    VARCHAR NOT NULL
);
"""


INSERT_ALERT = f"""
INSERT INTO {ALERTS_TABLE}
    (timestamp_us, detector, severity, entity, summary,
     window_start_us, window_end_us, evidence_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def _alert_to_row(a: Alert) -> tuple[int, str, str, str, str, int, int, str]:
    return (
        a.timestamp_us,
        a.detector,
        a.severity,
        a.entity,
        a.summary,
        a.window_start_us,
        a.window_end_us,
        json.dumps(a.evidence, default=str),
    )


def _row_to_alert(row: Sequence[Any]) -> Alert:
    ts, detector, severity, entity, summary, ws, we, ev_json = row
    try:
        evidence = json.loads(ev_json) if ev_json else {}
    except json.JSONDecodeError:
        evidence = {}
    return Alert(
        timestamp_us=int(ts),
        detector=str(detector),
        severity=str(severity),  # type: ignore[arg-type]
        entity=str(entity),
        summary=str(summary),
        window_start_us=int(ws),
        window_end_us=int(we),
        evidence=evidence,
    )


class AlertHistoryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: duckdb.DuckDBPyConnection = duckdb.connect(str(self.path))
        self._conn.execute(CREATE_ALERTS_TABLE)

    def __enter__(self) -> AlertHistoryStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def write(self, alert: Alert) -> None:
        self._conn.execute(INSERT_ALERT, _alert_to_row(alert))

    def write_batch(self, alerts: Iterable[Alert]) -> int:
        rows = [_alert_to_row(a) for a in alerts]
        if not rows:
            return 0
        self._conn.executemany(INSERT_ALERT, rows)
        return len(rows)

    def count(self) -> int:
        result = self._conn.execute(f"SELECT COUNT(*) FROM {ALERTS_TABLE}").fetchone()
        return 0 if result is None else int(result[0])

    def query_window(
        self,
        since_us: int,
        until_us: int,
        detector: str | None = None,
        severity: str | None = None,
        limit: int = 1000,
    ) -> list[Alert]:
        sql = (
            f"SELECT timestamp_us, detector, severity, entity, summary, "
            f"window_start_us, window_end_us, evidence_json FROM {ALERTS_TABLE} "
            "WHERE timestamp_us >= ? AND timestamp_us < ?"
        )
        params: list[Any] = [since_us, until_us]
        if detector is not None:
            sql += " AND detector = ?"
            params.append(detector)
        if severity is not None:
            sql += " AND severity = ?"
            params.append(severity)
        sql += " ORDER BY timestamp_us LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_alert(r) for r in rows]
