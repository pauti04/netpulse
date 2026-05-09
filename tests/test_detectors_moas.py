from __future__ import annotations

from netpulse.detectors.moas import MOASDetector
from netpulse.features.bgp import BGPWindowFeatures


def test_flags_prefix_with_multiple_origins() -> None:
    feats = BGPWindowFeatures(
        window_start_us=0,
        window_end_us=1_000_000,
        origins_by_prefix={"192.0.2.0/24": {64600, 64601}},
        announce_count_by_prefix={"192.0.2.0/24": 5},
    )

    alerts = MOASDetector().score(feats)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.detector == "moas"
    assert a.entity == "192.0.2.0/24"
    assert a.severity == "warning"
    assert a.evidence["origin_asns"] == [64600, 64601]
    assert a.evidence["announce_count"] == 5
    assert a.window_start_us == 0
    assert a.window_end_us == 1_000_000


def test_ignores_single_origin_prefixes() -> None:
    feats = BGPWindowFeatures(
        window_start_us=0,
        window_end_us=1_000_000,
        origins_by_prefix={"192.0.2.0/24": {64600}},
        announce_count_by_prefix={"192.0.2.0/24": 3},
    )
    assert MOASDetector().score(feats) == []


def test_respects_min_announce_count_threshold() -> None:
    feats = BGPWindowFeatures(
        window_start_us=0,
        window_end_us=1_000_000,
        origins_by_prefix={"192.0.2.0/24": {64600, 64601}},
        announce_count_by_prefix={"192.0.2.0/24": 1},
    )

    assert MOASDetector(min_announce_count=2).score(feats) == []
    assert len(MOASDetector(min_announce_count=1).score(feats)) == 1


def test_handles_multiple_prefixes_independently() -> None:
    feats = BGPWindowFeatures(
        window_start_us=0,
        window_end_us=1_000_000,
        origins_by_prefix={
            "192.0.2.0/24": {64600, 64601},  # MOAS
            "198.51.100.0/24": {64602},  # single origin
            "203.0.113.0/24": {64603, 64604, 64605},  # MOAS, three origins
        },
        announce_count_by_prefix={
            "192.0.2.0/24": 5,
            "198.51.100.0/24": 5,
            "203.0.113.0/24": 5,
        },
    )

    alerts = MOASDetector().score(feats)
    flagged = sorted(a.entity for a in alerts)
    assert flagged == ["192.0.2.0/24", "203.0.113.0/24"]
