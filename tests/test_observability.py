"""Tests for structured logging + request middleware."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from netpulse.api.app import build_app
from netpulse.api.metrics import MetricsRegistry
from netpulse.observability import (
    JsonFormatter,
    RequestLoggingMiddleware,
    configure_logging,
)
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord


def test_json_formatter_emits_single_line_json() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="x.py",
        lineno=10,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.request_id = "abc123"
    record.status = 200
    out = JsonFormatter().format(record)
    # Must be a single line of valid JSON.
    assert "\n" not in out
    payload = json.loads(out)
    assert payload["msg"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert payload["request_id"] == "abc123"
    assert payload["status"] == 200
    assert "ts" in payload


def test_configure_logging_is_idempotent() -> None:
    configure_logging(json_mode=True)
    first_handlers = list(logging.getLogger().handlers)
    configure_logging(json_mode=True)
    second_handlers = list(logging.getLogger().handlers)
    # Re-configuring should not stack handlers.
    assert len(second_handlers) == len(first_handlers) == 1


def test_request_middleware_logs_and_records_histogram() -> None:
    registry = MetricsRegistry()
    hist = registry.histogram("test_request_duration", "for testing")

    inner = FastAPI()

    @inner.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    inner.add_middleware(RequestLoggingMiddleware, duration_histogram=hist)

    # Capture log output by attaching a stream handler to the access logger.
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    access_logger = logging.getLogger("netpulse.access")
    access_logger.handlers = [handler]
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False

    client = TestClient(inner)
    resp = client.get("/ping")
    assert resp.status_code == 200
    # Middleware should attach x-request-id to every response.
    assert "x-request-id" in resp.headers

    handler.flush()
    log_lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    assert log_lines, "middleware did not log anything"
    payload = json.loads(log_lines[-1])
    assert payload["path"] == "/ping"
    assert payload["method"] == "GET"
    assert payload["status"] == 200
    assert payload["duration_ms"] >= 0
    assert isinstance(payload["request_id"], str) and len(payload["request_id"]) > 0

    # Histogram should have recorded one observation under the /ping endpoint.
    assert "/ping" in hist.series
    counts, total, n = hist.series["/ping"]
    assert n == 1
    assert total >= 0


def test_histogram_renders_in_prometheus_format() -> None:
    r = MetricsRegistry()
    h = r.histogram("netpulse_request_duration_seconds", "for testing")
    h.observe(0.002, label_value="/health")
    h.observe(0.030, label_value="/health")
    h.observe(0.300, label_value="/detect/bgp")

    out = r.render()
    assert "# TYPE netpulse_request_duration_seconds histogram" in out
    assert 'netpulse_request_duration_seconds_bucket{endpoint="/health",le="0.005"}' in out
    assert 'netpulse_request_duration_seconds_bucket{endpoint="/health",le="+Inf"} 2' in out
    assert 'netpulse_request_duration_seconds_count{endpoint="/health"} 2' in out
    # 0.030 is in (0.025, 0.05] so the 0.025 bucket has only the 0.002 sample.
    assert 'netpulse_request_duration_seconds_bucket{endpoint="/health",le="0.025"} 1' in out


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
                    prefix="203.0.113.0/22",
                    update_type="A",
                    origin_as=64500,
                    as_path="64500",
                )
            ]
        )
    return store_path, baseline_path


def test_ready_endpoint_returns_200_when_store_opens(
    store_and_baseline: tuple[Path, Path],
) -> None:
    store_path, baseline_path = store_and_baseline
    api = build_app(store_path=store_path, baseline_path=baseline_path)
    client = TestClient(api)
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"


def test_ready_endpoint_returns_503_when_store_unreadable(
    tmp_path: Path,
) -> None:
    """If the store file gets corrupted at runtime, /ready should fail."""
    store_path = tmp_path / "store.duckdb"
    with BGPStore(store_path) as s:
        s.write_batch(
            [
                BGPRecord(
                    timestamp_us=1,
                    collector="rrc00",
                    peer_as=0,
                    peer_ip="0.0.0.0",
                    prefix="1.0.0.0/24",
                    update_type="A",
                    origin_as=1,
                    as_path="1",
                )
            ]
        )
    api = build_app(store_path=store_path)
    client = TestClient(api)

    # Truncate the store file mid-life -- simulates a corrupt mount.
    store_path.write_bytes(b"garbage")

    resp = client.get("/ready")
    assert resp.status_code == 503
    assert "store not ready" in resp.json()["detail"]


def test_request_id_round_trips_header(
    store_and_baseline: tuple[Path, Path],
) -> None:
    """If the client passes x-request-id, the server echoes it back."""
    store_path, baseline_path = store_and_baseline
    api = build_app(store_path=store_path, baseline_path=baseline_path)
    client = TestClient(api)
    resp = client.get("/health", headers={"x-request-id": "trace-abc-123"})
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "trace-abc-123"


def test_histogram_appears_in_metrics_output(
    store_and_baseline: tuple[Path, Path],
) -> None:
    """After a few requests, /metrics should include the duration histogram."""
    store_path, baseline_path = store_and_baseline
    api = build_app(store_path=store_path, baseline_path=baseline_path)
    client = TestClient(api)
    # Drive a couple of requests through the middleware.
    for _ in range(3):
        client.get("/health")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "netpulse_request_duration_seconds" in body
    assert 'endpoint="/health"' in body
