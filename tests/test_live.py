"""Tests for the live-monitor core: the thread-safe feed + helpers."""

from __future__ import annotations

from collections import deque

from netpulse.ingest.stream import StreamUpdate
from netpulse.live.feed import Detection, DetectionFeed
from netpulse.live.monitor import _features_from_window, _is_signal


def _det(entity: str = "10.0.0.0/24") -> Detection:
    return Detection(ts_us=1, detector="moas", severity="warning", entity=entity, summary="s")


# ----- DetectionFeed -----


def test_feed_recent_is_newest_first_and_bounded() -> None:
    feed = DetectionFeed(maxlen=3)
    for i in range(5):
        feed.add([_det(f"10.0.{i}.0/24")])
    recent = feed.recent(10)
    assert len(recent) == 3  # bounded
    assert [d.entity for d in recent] == ["10.0.4.0/24", "10.0.3.0/24", "10.0.2.0/24"]


def test_feed_counters() -> None:
    feed = DetectionFeed()
    feed.note_updates(100, last_ts_us=5)
    feed.note_updates(50, last_ts_us=3)  # older ts shouldn't lower the max
    feed.note_window()
    feed.note_reconnect()
    feed.add([_det(), _det()])
    s = feed.stats()
    assert s["updates_seen"] == 150
    assert s["last_update_ts_us"] == 5
    assert s["windows_evaluated"] == 1
    assert s["reconnects"] == 1
    assert s["detections_total"] == 2
    assert s["buffered"] == 2


def test_feed_recent_limit() -> None:
    feed = DetectionFeed()
    for i in range(20):
        feed.add([_det(f"10.0.{i}.0/24")])
    assert len(feed.recent(5)) == 5


# ----- monitor helpers -----


class _FakeAlert:
    def __init__(self, detector: str, origins: list[int] | None = None) -> None:
        self.detector = detector
        self.entity = "x"
        self.evidence = {"origin_asns": origins} if origins is not None else {}


def test_is_signal_filters_low_origin_moas() -> None:
    assert _is_signal(_FakeAlert("moas", [1, 2])) is False  # 2 origins = legit multi-homing
    assert _is_signal(_FakeAlert("moas", [1, 2, 3])) is True  # 3+ is surfaced
    assert _is_signal(_FakeAlert("subprefix_hijack")) is True  # non-MOAS always passes
    assert _is_signal(_FakeAlert("origin_deaggregation")) is True


def test_features_from_window_aggregates() -> None:
    window: deque[StreamUpdate] = deque(
        [
            StreamUpdate(1_000, "h", 64500, "A", "10.0.0.0/24", 100),
            StreamUpdate(2_000, "h", 64500, "A", "10.0.0.0/24", 200),  # MOAS
            StreamUpdate(3_000, "h", 64500, "W", "10.9.0.0/24", None),
        ]
    )
    feats = _features_from_window(window)
    assert feats.origins_by_prefix["10.0.0.0/24"] == {100, 200}
    assert feats.announce_count_by_prefix["10.0.0.0/24"] == 2
    assert feats.withdraw_count_by_prefix["10.9.0.0/24"] == 1
    assert feats.window_start_us == 1_000
    assert feats.window_end_us == 3_000


def test_features_from_empty_window() -> None:
    feats = _features_from_window(deque())
    assert feats.origins_by_prefix == {}
    assert feats.window_start_us == 0
