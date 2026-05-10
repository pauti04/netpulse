from __future__ import annotations

from netpulse.alerts import Alert
from netpulse.detectors.fusion import MultiSignalCorrelator


def _bgp_alert(detector: str = "route_leak") -> Alert:
    return Alert(
        timestamp_us=1_700_000_000_000_000,
        detector=detector,
        severity="warning",
        entity="path",
        summary="x",
        window_start_us=0,
        window_end_us=1_700_000_000_000_000,
    )


def test_fusion_emits_when_both_signals_fire() -> None:
    c = MultiSignalCorrelator(rtt_jump_factor=1.15)
    fused = c.fuse(
        bgp_alerts=[_bgp_alert("route_leak"), _bgp_alert("subprefix_hijack")],
        window_start_us=0,
        window_end_us=600_000_000,
        atlas_baseline_median_rtt_ms=40.0,
        atlas_window_median_rtt_ms=50.0,
        atlas_msm_id=1999544,
    )
    assert len(fused) == 1
    a = fused[0]
    assert a.detector == "multi_signal_fusion"
    assert a.severity == "critical"
    assert a.entity == "msm:1999544"
    assert a.evidence["n_bgp_alerts"] == 2
    assert a.evidence["bgp_alert_detectors"] == ["route_leak", "subprefix_hijack"]
    assert a.evidence["rtt_jump_factor"] == 50.0 / 40.0


def test_fusion_silent_without_bgp_alerts() -> None:
    c = MultiSignalCorrelator()
    assert (
        c.fuse(
            bgp_alerts=[],
            window_start_us=0,
            window_end_us=100,
            atlas_baseline_median_rtt_ms=40.0,
            atlas_window_median_rtt_ms=80.0,
        )
        == []
    )


def test_fusion_silent_when_latency_not_elevated() -> None:
    c = MultiSignalCorrelator(rtt_jump_factor=1.15)
    assert (
        c.fuse(
            bgp_alerts=[_bgp_alert()],
            window_start_us=0,
            window_end_us=100,
            atlas_baseline_median_rtt_ms=40.0,
            atlas_window_median_rtt_ms=44.0,  # 1.10x, below 1.15
        )
        == []
    )


def test_fusion_silent_for_zero_baseline() -> None:
    c = MultiSignalCorrelator()
    assert (
        c.fuse(
            bgp_alerts=[_bgp_alert()],
            window_start_us=0,
            window_end_us=100,
            atlas_baseline_median_rtt_ms=0.0,
            atlas_window_median_rtt_ms=80.0,
        )
        == []
    )
