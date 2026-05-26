"""Tests for the origin-deaggregation detector.

Captures three shapes:
  - Normal-volume single-origin operator: no alert.
  - High-volume multi-/16 ISP announcing covering supernets only: no alert.
  - Telekom-Malaysia-2015-style burst of /23 more-specifics: alert.
"""

from __future__ import annotations

from netpulse.detectors.origin_deaggregation import OriginDeaggregationDetector
from netpulse.features.bgp import BGPWindowFeatures


def _make_feats(origins: dict[str, set[int]]) -> BGPWindowFeatures:
    return BGPWindowFeatures(
        window_start_us=0,
        window_end_us=1_000_000,
        origins_by_prefix=origins,
    )


def test_ignores_small_origin() -> None:
    """A handful of prefixes from one origin is not deaggregation."""
    origins = {f"10.{i}.0.0/24": {64600} for i in range(20)}
    alerts = OriginDeaggregationDetector().score(_make_feats(origins))
    assert alerts == []


def test_ignores_supernet_only_origin() -> None:
    """An ISP with many /16s but no /23+ should not fire."""
    origins = {f"10.{i}.0.0/16": {64600} for i in range(300)}
    alerts = OriginDeaggregationDetector().score(_make_feats(origins))
    # 300 prefixes from one origin, 0 of which are /23+
    assert alerts == []


def test_fires_on_deaggregation_burst() -> None:
    """The canonical TM-2015 shape: hundreds of /23s from one origin."""
    origins = {f"10.{i // 256}.{i % 256}.0/23": {64600} for i in range(250)}
    alerts = OriginDeaggregationDetector().score(_make_feats(origins))
    assert len(alerts) == 1
    a = alerts[0]
    assert a.detector == "origin_deaggregation"
    assert a.entity == "AS64600"
    assert a.severity == "warning"
    assert a.evidence["distinct_prefixes"] == 250
    assert a.evidence["long_prefix_count"] == 250
    assert a.evidence["long_prefix_share"] == 1.0


def test_threshold_share_blocks_mixed_origin() -> None:
    """An origin with mostly /16s + a few /24s should NOT fire."""
    origins = {f"10.{i}.0.0/16": {64600} for i in range(200)}
    # 50 /24s mixed in => 50 / 250 = 20% long → below default 70%.
    origins.update({f"172.16.{i}.0/24": {64600} for i in range(50)})
    alerts = OriginDeaggregationDetector().score(_make_feats(origins))
    assert alerts == []


def test_custom_thresholds() -> None:
    """Tuning lowers the bar so smaller windows trip the detector."""
    origins = {f"10.{i // 256}.{i % 256}.0/24": {64600} for i in range(50)}
    detector = OriginDeaggregationDetector(min_distinct_prefixes=40, min_long_prefix_share=0.5)
    alerts = detector.score(_make_feats(origins))
    assert len(alerts) == 1
    assert alerts[0].evidence["distinct_prefixes"] == 50


def test_one_alert_per_origin_in_multi_origin_burst() -> None:
    """Two ASes both deaggregating produce two alerts."""
    origins = {f"10.{i // 256}.{i % 256}.0/23": {64600} for i in range(200)}
    origins.update({f"172.{i // 256}.{i % 256}.0/24": {64601} for i in range(200)})
    alerts = OriginDeaggregationDetector().score(_make_feats(origins))
    by_entity = {a.entity for a in alerts}
    assert by_entity == {"AS64600", "AS64601"}
