from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import duckdb

from netpulse.storage.schema import (
    BGP_RECORDS_TABLE,
    CREATE_BGP_RECORDS_TABLE,
    INSERT_BGP_RECORD,
    BGPRecord,
    record_to_row,
)


class BGPStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: duckdb.DuckDBPyConnection = duckdb.connect(str(self.path))
        self._conn.execute(CREATE_BGP_RECORDS_TABLE)

    def __enter__(self) -> BGPStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def write_batch(self, records: Iterable[BGPRecord]) -> int:
        rows = [record_to_row(r) for r in records]
        if not rows:
            return 0
        self._conn.executemany(INSERT_BGP_RECORD, rows)
        return len(rows)

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple[Any, ...]]:
        cur = self._conn.execute(sql, params) if params is not None else self._conn.execute(sql)
        return cur.fetchall()

    def count(self) -> int:
        result = self._conn.execute(f"SELECT COUNT(*) FROM {BGP_RECORDS_TABLE}").fetchone()
        return 0 if result is None else int(result[0])
