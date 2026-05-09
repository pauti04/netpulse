from __future__ import annotations

from pathlib import Path

import pytest

from netpulse.benchmark.incident import Incident
from netpulse.benchmark.metrics import summarize
from netpulse.benchmark.replay import ReplayResult, replay_bgp_incident
from netpulse.detectors.moas import MOASDetector
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord


def _rec(ts: int, prefix: str, origin: int) -> BGPRecord:
    return BGPRecord(
        timestamp_us=ts,
        collector="rrc00",
        peer_as=64500,
        peer_ip="192.0.2.1",
        prefix=prefix,
        update_type="A",
        origin_as=origin,
        as_path=str(origin),
    )


def _incident(prefix: str | None = "192.0.2.0/24", **overrides: object) -> Incident:
    base: dict[str, object] = {
        "id": "synthetic",
        "name": "synthetic",
        "kind": "hijack",
        "start_us": 0,
        "end_us": 600_000_000,
        "expected_detectors": ["moas"],
        "source_url": "https://example.test",
        "prefix": prefix,
    }
    base.update(overrides)
    return Incident(**base)  # type: ignore[arg-type]


def test_replay_detects_moas_and_reports_chunk_aligned_latency(tmp_path: Path) -> None:
    # MOAS appears in the third 60s chunk: first origin in chunks 0-1, second
    # origin appears at t=125s, so the chunk ending at 180s should be the
    # first one to expose two distinct origins.
    with BGPStore(tmp_path / "bgp.duckdb") as store:
        store.write_batch(
            [
                _rec(10_000_000, "192.0.2.0/24", 64600),
                _rec(70_000_000, "192.0.2.0/24", 64600),
                _rec(125_000_000, "192.0.2.0/24", 64601),
                _rec(160_000_000, "192.0.2.0/24", 64601),
            ]
        )
        result = replay_bgp_incident(
            _incident(),
            store,
            [MOASDetector()],
            chunk_us=60_000_000,
        )

    assert result.detected is True
    assert result.latency_us == 180_000_000  # third chunk ends at 180s
    assert any(a.entity == "192.0.2.0/24" for a in result.alerts)


def test_replay_misses_when_only_single_origin_seen(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "bgp.duckdb") as store:
        store.write_batch(
            [
                _rec(10_000_000, "192.0.2.0/24", 64600),
                _rec(70_000_000, "192.0.2.0/24", 64600),
            ]
        )
        result = replay_bgp_incident(
            _incident(),
            store,
            [MOASDetector()],
            chunk_us=60_000_000,
        )

    assert result.detected is False
    assert result.latency_us is None


def test_replay_filters_alerts_to_incident_prefix(tmp_path: Path) -> None:
    # MOAS on a different prefix than the incident's — should not count as
    # a detection even though an alert is captured.
    with BGPStore(tmp_path / "bgp.duckdb") as store:
        store.write_batch(
            [
                _rec(10_000_000, "203.0.113.0/24", 64600),
                _rec(20_000_000, "203.0.113.0/24", 64601),
            ]
        )
        result = replay_bgp_incident(
            _incident(prefix="192.0.2.0/24"),
            store,
            [MOASDetector()],
            chunk_us=60_000_000,
        )

    assert result.detected is False
    assert any(a.entity == "203.0.113.0/24" for a in result.alerts)


def test_replay_rejects_zero_chunk(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "bgp.duckdb") as store, pytest.raises(ValueError):
        replay_bgp_incident(_incident(), store, [MOASDetector()], chunk_us=0)


def test_summarize_aggregates_across_results() -> None:
    results = [
        ReplayResult(incident_id="a", detected=True, latency_us=120_000_000),
        ReplayResult(incident_id="b", detected=True, latency_us=60_000_000),
        ReplayResult(incident_id="c", detected=False, latency_us=None),
    ]
    s = summarize(results)
    assert s.total_incidents == 3
    assert s.detected_count == 2
    assert s.detection_rate == pytest.approx(2 / 3)
    assert s.mean_latency_us == pytest.approx(90_000_000)
    assert s.median_latency_us == pytest.approx(90_000_000)


def test_summarize_handles_no_detections() -> None:
    results = [ReplayResult(incident_id="a", detected=False, latency_us=None)]
    s = summarize(results)
    assert s.detected_count == 0
    assert s.detection_rate == 0.0
    assert s.mean_latency_us is None
    assert s.median_latency_us is None


def test_summarize_handles_empty_input() -> None:
    s = summarize([])
    assert s.total_incidents == 0
    assert s.detection_rate == 0.0
