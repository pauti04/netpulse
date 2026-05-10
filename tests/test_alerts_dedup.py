from __future__ import annotations

from netpulse.alerts import Alert
from netpulse.alerts.dedup import AlertDeduper


def _alert(ts_us: int, entity: str = "192.0.2.0/24", detector: str = "moas") -> Alert:
    return Alert(
        timestamp_us=ts_us,
        detector=detector,
        severity="warning",
        entity=entity,
        summary="x",
        window_start_us=0,
        window_end_us=ts_us,
    )


def test_first_alert_always_emits() -> None:
    d = AlertDeduper(cooldown_us=10_000_000)
    assert d.should_emit(_alert(0))


def test_duplicate_within_cooldown_suppressed() -> None:
    d = AlertDeduper(cooldown_us=10_000_000)
    d.should_emit(_alert(0))
    assert not d.should_emit(_alert(5_000_000))  # same fingerprint, 5s later


def test_duplicate_after_cooldown_emits() -> None:
    d = AlertDeduper(cooldown_us=10_000_000)
    d.should_emit(_alert(0))
    assert d.should_emit(_alert(11_000_000))  # 11s later -> past cooldown


def test_distinct_entities_do_not_dedupe_each_other() -> None:
    d = AlertDeduper(cooldown_us=10_000_000)
    assert d.should_emit(_alert(0, entity="192.0.2.0/24"))
    assert d.should_emit(_alert(1_000_000, entity="203.0.113.0/24"))


def test_filter_streams_through_iterable() -> None:
    d = AlertDeduper(cooldown_us=10_000_000)
    inputs = [
        _alert(0, entity="a"),
        _alert(1_000_000, entity="a"),  # dup
        _alert(2_000_000, entity="b"),
        _alert(20_000_000, entity="a"),  # past cooldown -> emit again
    ]
    out = list(d.filter(inputs))
    assert [a.entity for a in out] == ["a", "b", "a"]
