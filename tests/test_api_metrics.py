from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netpulse.api.app import build_app
from netpulse.api.metrics import MetricsRegistry
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord


def test_metrics_registry_renders_counter_and_gauge() -> None:
    r = MetricsRegistry()
    c = r.counter("test_counter_total", "for testing")
    c.inc()
    c.inc(label_value="moas")
    c.inc(label_value="moas")
    c.inc(label_value="subprefix_hijack")
    g = r.gauge("test_gauge", "for testing")
    g.set(42.5)

    out = r.render()
    assert "# HELP test_counter_total for testing" in out
    assert "# TYPE test_counter_total counter" in out
    assert 'test_counter_total{detector="moas"} 2' in out
    assert 'test_counter_total{detector="subprefix_hijack"} 1' in out
    assert "test_gauge 42.5" in out


@pytest.fixture
def store_and_baseline(tmp_path: Path) -> tuple[Path, Path]:
    store_path = tmp_path / "store.duckdb"
    baseline_path = tmp_path / "baseline.duckdb"
    base_us = 1_700_000_000_000_000
    with BGPStore(store_path) as s:
        s.write_batch(
            [
                BGPRecord(
                    timestamp_us=base_us,
                    collector="rrc00",
                    peer_as=64500,
                    peer_ip="192.0.2.1",
                    prefix="203.0.113.0/24",
                    update_type="A",
                    origin_as=64601,
                    as_path="64601",
                )
            ]
        )
    with BGPStore(baseline_path) as bs:
        bs.write_batch(
            [
                BGPRecord(
                    timestamp_us=0,
                    collector="rrc00",
                    peer_as=0,
                    peer_ip="0.0.0.0",
                    prefix="203.0.112.0/21",
                    update_type="A",
                    origin_as=64600,
                    as_path="64600",
                )
            ]
        )
    return store_path, baseline_path


def test_metrics_endpoint_is_served(store_and_baseline: tuple[Path, Path]) -> None:
    store_path, baseline_path = store_and_baseline
    api = build_app(store_path=store_path, baseline_path=baseline_path)
    client = TestClient(api)

    # Hit a few endpoints to populate counters
    client.get("/health")
    client.post(
        "/detect/bgp",
        json={"start_iso": "2023-11-14T22:13:20Z", "duration_s": 60},
    )

    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "netpulse_requests_total" in body
    assert 'netpulse_requests_total{detector="health"}' in body
    assert 'netpulse_requests_total{detector="detect_bgp"}' in body
    assert "netpulse_alerts_total" in body
    assert "netpulse_baseline_prefixes 1" in body
