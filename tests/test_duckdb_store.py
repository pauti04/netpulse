"""Tests for BGPStore, including read-only multi-opener support.

The read-only path matters for multi-worker serving: DuckDB grants the
write lock to only one opener, so worker processes must open read-only
to share a store. These tests assert read-only opens work, allow
concurrent openers, and reject writes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord


def _rec(ts: int) -> BGPRecord:
    return BGPRecord(
        timestamp_us=ts,
        collector="t",
        peer_as=1,
        peer_ip="192.0.2.1",
        prefix="10.0.0.0/24",
        update_type="A",
        origin_as=64500,
        as_path="64500",
    )


def test_write_then_read(tmp_path: Path) -> None:
    p = tmp_path / "s.duckdb"
    with BGPStore(p) as store:
        assert store.write_batch([_rec(1), _rec(2)]) == 2
        assert store.count() == 2


def test_read_only_can_query(tmp_path: Path) -> None:
    p = tmp_path / "s.duckdb"
    with BGPStore(p) as store:
        store.write_batch([_rec(1)])
    with BGPStore(p, read_only=True) as ro:
        assert ro.read_only is True
        assert ro.count() == 1


def test_two_concurrent_read_only_openers(tmp_path: Path) -> None:
    # The whole point: multiple processes/handles share one store.
    p = tmp_path / "s.duckdb"
    with BGPStore(p) as store:
        store.write_batch([_rec(1), _rec(2), _rec(3)])
    a = BGPStore(p, read_only=True)
    b = BGPStore(p, read_only=True)
    try:
        assert a.count() == 3
        assert b.count() == 3
    finally:
        a.close()
        b.close()


def test_read_only_rejects_writes(tmp_path: Path) -> None:
    p = tmp_path / "s.duckdb"
    with BGPStore(p) as store:
        store.write_batch([_rec(1)])
    with BGPStore(p, read_only=True) as ro, pytest.raises(Exception):  # noqa: PT011, B017
        ro.write_batch([_rec(2)])
