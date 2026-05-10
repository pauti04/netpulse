from __future__ import annotations

from pathlib import Path

from netpulse.alerts import Alert
from netpulse.alerts.store import AlertHistoryStore


def _alert(ts_us: int, detector: str = "moas", entity: str = "192.0.2.0/24") -> Alert:
    return Alert(
        timestamp_us=ts_us,
        detector=detector,
        severity="warning",
        entity=entity,
        summary="x",
        window_start_us=ts_us - 60_000_000,
        window_end_us=ts_us,
        evidence={"foo": "bar", "n": 7},
    )


def test_round_trip_single(tmp_path: Path) -> None:
    with AlertHistoryStore(tmp_path / "alerts.duckdb") as s:
        s.write(_alert(1_000_000))
        assert s.count() == 1
        out = s.query_window(0, 2_000_000)
    assert len(out) == 1
    assert out[0].detector == "moas"
    assert out[0].evidence == {"foo": "bar", "n": 7}


def test_query_filters_by_time(tmp_path: Path) -> None:
    with AlertHistoryStore(tmp_path / "alerts.duckdb") as s:
        s.write_batch([_alert(1_000_000), _alert(5_000_000), _alert(10_000_000)])
        out = s.query_window(2_000_000, 8_000_000)
    assert [a.timestamp_us for a in out] == [5_000_000]


def test_query_filters_by_detector(tmp_path: Path) -> None:
    with AlertHistoryStore(tmp_path / "alerts.duckdb") as s:
        s.write_batch(
            [
                _alert(1_000_000, detector="moas"),
                _alert(2_000_000, detector="subprefix_hijack"),
                _alert(3_000_000, detector="moas"),
            ]
        )
        out = s.query_window(0, 10_000_000, detector="moas")
    assert sorted(a.timestamp_us for a in out) == [1_000_000, 3_000_000]


def test_query_filters_by_severity(tmp_path: Path) -> None:
    with AlertHistoryStore(tmp_path / "alerts.duckdb") as s:
        a1 = _alert(1_000_000)
        a2 = _alert(2_000_000)
        a2.severity = "critical"
        s.write_batch([a1, a2])
        out = s.query_window(0, 10_000_000, severity="critical")
    assert [a.severity for a in out] == ["critical"]


def test_write_batch_empty_is_noop(tmp_path: Path) -> None:
    with AlertHistoryStore(tmp_path / "alerts.duckdb") as s:
        assert s.write_batch([]) == 0
        assert s.count() == 0
