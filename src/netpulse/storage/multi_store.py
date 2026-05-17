"""Multi-store BGP view: run detectors over a UNION of multiple stores.

A single RIS collector sees only its peer set. Operators interested in
whether an event reached *any* monitored vantage point need to merge
evidence across collectors. The Cloudflare/2024 finding documented in
BENCHMARK.md is a concrete example of why one-collector views miss
incidents.

This module exposes :class:`MultiStoreBGPView`, a read-only object that
quacks like :class:`netpulse.storage.duckdb_store.BGPStore`: it
implements ``query()`` and ``count()`` over a logical UNION ALL of every
attached store's ``bgp_records`` table, and a small ``count_by_source``
helper for the per-collector breakdown.

Implementation: open an in-memory DuckDB connection, ATTACH each
underlying store as a read-only catalog, and define a view
``bgp_records`` that ``UNION ALL``-s them together. Existing
feature-extraction and replay code that takes a ``BGPStore`` works
unchanged because they only call ``store.query("... FROM bgp_records
...")`` / ``store.count()``.

Identical records seen at multiple collectors are *not* de-duplicated.
That's intentional: feature extraction's per-prefix-origin aggregation
(``GROUP BY prefix, origin_as, update_type``) already collapses them
into a single observation, and per-record streaming replay stops at the
first occurrence in time order — so the union sees the union of evidence
without inflating MOAS counts.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb


class MultiStoreBGPView:
    """Read-only union view over multiple BGP DuckDB stores."""

    def __init__(self, paths: Sequence[str | Path]) -> None:
        if not paths:
            raise ValueError("at least one store path is required")
        self._sources: list[tuple[str, Path]] = []
        self._conn: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")

        for index, raw_path in enumerate(paths):
            path = Path(raw_path)
            if not path.exists():
                raise FileNotFoundError(f"store {path} does not exist")
            alias = f"src_{index}"
            self._conn.execute(
                f"ATTACH '{path.as_posix()}' AS {alias} (READ_ONLY)",
            )
            self._sources.append((alias, path))

        union_sql = " UNION ALL ".join(
            f"SELECT '{alias}' AS _source, * FROM {alias}.bgp_records"
            for alias, _ in self._sources
        )
        self._conn.execute(f"CREATE VIEW bgp_records AS {union_sql}")

    def __enter__(self) -> MultiStoreBGPView:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple[Any, ...]]:
        cur = self._conn.execute(sql, params) if params is not None else self._conn.execute(sql)
        return cur.fetchall()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM bgp_records").fetchone()
        return 0 if row is None else int(row[0])

    def count_by_source(self) -> list[tuple[str, str, int]]:
        """Per-source row counts. Returns ``[(alias, path, n_records), ...]``."""
        out: list[tuple[str, str, int]] = []
        for alias, path in self._sources:
            row = self._conn.execute(
                f"SELECT COUNT(*) FROM {alias}.bgp_records"
            ).fetchone()
            n = 0 if row is None else int(row[0])
            out.append((alias, str(path), n))
        return out

    @property
    def sources(self) -> list[Path]:
        return [p for _, p in self._sources]
