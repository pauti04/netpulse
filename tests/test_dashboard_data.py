"""Tests for the dashboard data layer (no Streamlit runtime)."""

from __future__ import annotations

from pathlib import Path

import pytest

from netpulse.alerts import Alert
from netpulse.alerts.store import AlertHistoryStore
from netpulse.dashboard.data import (
    bucketize,
    load_alerts,
    summarize_window,
)


def _alert(
    ts_us: int,
    detector: str = "moas",
    severity: str = "warning",
    entity: str = "1.2.3.0/24",
) -> Alert:
    return Alert(
        timestamp_us=ts_us,
        detector=detector,
        severity=severity,  # type: ignore[arg-type]
        entity=entity,
        summary=f"{detector} on {entity}",
        window_start_us=ts_us,
        window_end_us=ts_us + 60_000_000,
        evidence={},
    )


def test_bucketize_groups_into_uniform_buckets() -> None:
    one_sec = 1_000_000
    alerts = [
        _alert(ts_us=0 * one_sec),
        _alert(ts_us=2 * one_sec),
        _alert(ts_us=5 * one_sec),
        _alert(ts_us=11 * one_sec),
    ]
    buckets = bucketize(
        alerts,
        bucket_size_us=3 * one_sec,
        window_start_us=0,
        window_end_us=12 * one_sec,
    )
    # Window 0..12s with 3-s buckets -> 4 buckets:
    # [0,3): 2  | [3,6): 1  | [6,9): 0  | [9,12): 1
    assert [b.count for b in buckets] == [2, 1, 0, 1]
    assert buckets[0].bucket_start_us == 0
    assert buckets[-1].bucket_end_us == 12 * one_sec


def test_bucketize_emits_empty_buckets_when_no_alerts_fall_in() -> None:
    one_sec = 1_000_000
    buckets = bucketize(
        [],
        bucket_size_us=one_sec,
        window_start_us=0,
        window_end_us=5 * one_sec,
    )
    assert len(buckets) == 5
    assert all(b.count == 0 for b in buckets)


def test_bucketize_ignores_alerts_outside_window() -> None:
    one_sec = 1_000_000
    alerts = [
        _alert(ts_us=-1 * one_sec),  # before start
        _alert(ts_us=0),
        _alert(ts_us=4 * one_sec),
        _alert(ts_us=10 * one_sec),  # at end -> excluded (right-open)
    ]
    buckets = bucketize(
        alerts,
        bucket_size_us=2 * one_sec,
        window_start_us=0,
        window_end_us=10 * one_sec,
    )
    total = sum(b.count for b in buckets)
    assert total == 2  # only ts_us=0 and ts_us=4_000_000 fall inside


def test_bucketize_rejects_nonpositive_bucket() -> None:
    with pytest.raises(ValueError):
        bucketize([], bucket_size_us=0, window_start_us=0, window_end_us=10)


def test_bucketize_rejects_empty_window() -> None:
    with pytest.raises(ValueError):
        bucketize([], bucket_size_us=1, window_start_us=10, window_end_us=10)


def test_summarize_window_empty() -> None:
    s = summarize_window([])
    assert s.total == 0
    assert s.first_us is None and s.last_us is None
    assert s.by_detector == []
    assert s.by_severity == []
    assert s.top_entities == []


def test_summarize_window_groups_and_sorts() -> None:
    alerts = [
        _alert(ts_us=10, detector="moas", severity="warning", entity="a/24"),
        _alert(ts_us=20, detector="moas", severity="warning", entity="a/24"),
        _alert(ts_us=30, detector="subprefix_hijack", severity="critical", entity="b/24"),
        _alert(ts_us=40, detector="moas", severity="info", entity="c/24"),
    ]
    s = summarize_window(alerts)
    assert s.total == 4
    assert s.first_us == 10 and s.last_us == 40
    # Sorted by count desc, then by name asc.
    assert s.by_detector[0].detector == "moas"
    assert s.by_detector[0].count == 3
    assert s.by_detector[1].detector == "subprefix_hijack"
    assert s.by_severity[0].severity == "warning"
    assert s.by_severity[0].count == 2
    # Top entity: a/24 has 2; the others tie at 1.
    assert s.top_entities[0] == ("a/24", 2)


def test_load_alerts_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "alerts.duckdb"
    with AlertHistoryStore(db) as hist:
        hist.write_batch(
            [
                _alert(ts_us=1_000_000, detector="moas"),
                _alert(ts_us=2_000_000, detector="subprefix_hijack", severity="critical"),
                _alert(ts_us=3_000_000, detector="moas"),
            ]
        )

    all_in_window = load_alerts(db, since_us=0, until_us=10_000_000)
    assert len(all_in_window) == 3

    only_moas = load_alerts(db, since_us=0, until_us=10_000_000, detector="moas")
    assert len(only_moas) == 2

    only_critical = load_alerts(db, since_us=0, until_us=10_000_000, severity="critical")
    assert len(only_critical) == 1
    assert only_critical[0].detector == "subprefix_hijack"

    narrow = load_alerts(db, since_us=2_000_000, until_us=3_000_000)
    assert len(narrow) == 1
    assert narrow[0].timestamp_us == 2_000_000
