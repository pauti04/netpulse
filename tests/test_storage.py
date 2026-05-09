from __future__ import annotations

from pathlib import Path

from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGP_RECORDS_TABLE, BGPRecord


def _make_record(i: int) -> BGPRecord:
    return BGPRecord(
        timestamp_us=1_700_000_000_000_000 + i,
        collector="rrc00",
        peer_as=64500 + (i % 5),
        peer_ip=f"192.0.2.{i % 256}",
        prefix=f"203.0.113.{i % 256}/24",
        update_type="A" if i % 2 == 0 else "W",
        origin_as=64600 + (i % 7) if i % 2 == 0 else None,
        as_path=f"64500 64550 {64600 + (i % 7)}" if i % 2 == 0 else None,
        communities="64500:1 64500:2" if i % 3 == 0 else None,
    )


def test_schema_is_created_on_open(tmp_path: Path) -> None:
    store = BGPStore(tmp_path / "bgp.duckdb")
    try:
        tables = store.query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        )
    finally:
        store.close()
    assert (BGP_RECORDS_TABLE,) in tables


def test_round_trip_100_records(tmp_path: Path) -> None:
    path = tmp_path / "bgp.duckdb"
    records = [_make_record(i) for i in range(100)]

    with BGPStore(path) as store:
        written = store.write_batch(records)
        assert written == 100
        assert store.count() == 100

        rows = store.query(
            f"SELECT timestamp_us, peer_as, prefix, update_type, origin_as "
            f"FROM {BGP_RECORDS_TABLE} ORDER BY timestamp_us"
        )

    assert len(rows) == 100
    assert rows[0][0] == records[0].timestamp_us
    assert rows[0][3] == records[0].update_type
    # Withdrawal records (odd i) should have null origin_as.
    assert rows[1][4] is None


def test_count_starts_at_zero_and_increments(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "bgp.duckdb") as store:
        assert store.count() == 0
        store.write_batch([_make_record(0), _make_record(1)])
        assert store.count() == 2
        store.write_batch([_make_record(2)])
        assert store.count() == 3


def test_write_batch_empty_is_noop(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "bgp.duckdb") as store:
        assert store.write_batch([]) == 0
        assert store.count() == 0
