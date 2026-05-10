from __future__ import annotations

from pathlib import Path

from netpulse.detectors.atlas_loss import AtlasLossSpikeDetector
from netpulse.features.atlas import AtlasPingWindowFeatures, extract_atlas_features
from netpulse.storage.atlas_schema import AtlasPingRecord
from netpulse.storage.atlas_store import AtlasPingStore


def _ping(prb: int, sent: int, rcvd: int, ts_us: int = 1_700_000_000_000_000) -> AtlasPingRecord:
    return AtlasPingRecord(
        timestamp_us=ts_us,
        msm_id=1001,
        prb_id=prb,
        dst_addr="193.0.14.129",
        sent=sent,
        rcvd=rcvd,
        avg_rtt_ms=20.0 if rcvd > 0 else None,
    )


def test_atlas_store_round_trips_records(tmp_path: Path) -> None:
    with AtlasPingStore(tmp_path / "atlas.duckdb") as store:
        store.write_batch([_ping(1, 3, 3), _ping(2, 3, 0)])
        assert store.count() == 2


def test_extract_features_counts_loss_correctly(tmp_path: Path) -> None:
    with AtlasPingStore(tmp_path / "atlas.duckdb") as store:
        store.write_batch(
            [
                _ping(1, 3, 3),  # ok
                _ping(2, 3, 0),  # full loss
                _ping(3, 3, 1),  # partial loss
                _ping(4, 3, 3),  # ok
            ]
        )
        feats = extract_atlas_features(
            store,
            msm_id=1001,
            start_us=1_700_000_000_000_000,
            end_us=1_700_000_000_000_001,
        )

    assert feats.n_results == 4
    assert feats.n_full_loss == 1
    assert feats.n_partial_loss == 1
    assert feats.full_loss_rate == 0.25


def test_loss_spike_fires_above_threshold() -> None:
    feats = AtlasPingWindowFeatures(
        window_start_us=0,
        window_end_us=240_000_000,
        msm_id=1001,
        n_results=200,
        n_full_loss=60,
        n_partial_loss=10,
    )

    alerts = AtlasLossSpikeDetector().score(feats)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.detector == "atlas_loss_spike"
    assert a.entity == "msm:1001"
    assert a.severity == "critical"
    assert a.evidence["n_full_loss"] == 60


def test_loss_spike_silent_when_below_threshold() -> None:
    feats = AtlasPingWindowFeatures(
        window_start_us=0,
        window_end_us=240_000_000,
        msm_id=1001,
        n_results=200,
        n_full_loss=4,
        n_partial_loss=2,
    )
    assert AtlasLossSpikeDetector().score(feats) == []


def test_loss_spike_silent_for_tiny_samples() -> None:
    feats = AtlasPingWindowFeatures(
        window_start_us=0,
        window_end_us=240_000_000,
        msm_id=1001,
        n_results=10,
        n_full_loss=8,
        n_partial_loss=0,
    )
    # Even 80% loss is suppressed when fewer than min_results probes report.
    assert AtlasLossSpikeDetector(min_results=100).score(feats) == []
