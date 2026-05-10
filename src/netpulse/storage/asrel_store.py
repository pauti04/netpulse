from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import duckdb

from netpulse.storage.asrel_schema import (
    ASREL_TABLE,
    CREATE_ASREL_TABLE,
    INSERT_ASREL,
    ASRelationship,
    asrel_to_row,
)


class ASRelStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: duckdb.DuckDBPyConnection = duckdb.connect(str(self.path))
        self._conn.execute(CREATE_ASREL_TABLE)

    def __enter__(self) -> ASRelStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def write_batch(self, records: Iterable[ASRelationship]) -> int:
        rows = [asrel_to_row(r) for r in records]
        if not rows:
            return 0
        self._conn.executemany(INSERT_ASREL, rows)
        return len(rows)

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple[Any, ...]]:
        cur = self._conn.execute(sql, params) if params is not None else self._conn.execute(sql)
        return cur.fetchall()

    def count(self) -> int:
        result = self._conn.execute(f"SELECT COUNT(*) FROM {ASREL_TABLE}").fetchone()
        return 0 if result is None else int(result[0])
