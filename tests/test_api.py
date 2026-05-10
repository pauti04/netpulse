from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netpulse.api.app import build_app
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord


@pytest.fixture
def hijack_store_and_baseline(tmp_path: Path) -> tuple[Path, Path]:
    """Build a tiny store with a synthetic sub-prefix hijack and matching baseline."""
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
                    origin_as=64601,  # unauthorized origin
                    as_path="64601",
                ),
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
                    origin_as=64600,  # legit
                    as_path="64600",
                ),
            ]
        )

    return store_path, baseline_path


def test_health_reports_baseline_size(hijack_store_and_baseline: tuple[Path, Path]) -> None:
    store_path, baseline_path = hijack_store_and_baseline
    api = build_app(store_path=store_path, baseline_path=baseline_path)

    client = TestClient(api)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["baseline_prefixes"] == 1


def test_detect_bgp_returns_subprefix_alert(
    hijack_store_and_baseline: tuple[Path, Path],
) -> None:
    store_path, baseline_path = hijack_store_and_baseline
    api = build_app(store_path=store_path, baseline_path=baseline_path)
    client = TestClient(api)

    r = client.post(
        "/detect/bgp",
        json={
            "start_iso": "2023-11-14T22:13:20Z",  # = 1_700_000_000 epoch s
            "duration_s": 60,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["distinct_prefixes"] == 1
    detectors_fired = sorted({a["detector"] for a in body["alerts"]})
    assert "subprefix_hijack" in detectors_fired
    sub = next(a for a in body["alerts"] if a["detector"] == "subprefix_hijack")
    assert sub["entity"] == "203.0.113.0/24"
    assert sub["severity"] == "critical"


def test_detect_bgp_rejects_bad_start_iso(
    hijack_store_and_baseline: tuple[Path, Path],
) -> None:
    store_path, baseline_path = hijack_store_and_baseline
    api = build_app(store_path=store_path, baseline_path=baseline_path)
    client = TestClient(api)

    r = client.post(
        "/detect/bgp",
        json={"start_iso": "not-a-date", "duration_s": 60},
    )
    assert r.status_code == 400


def test_build_app_rejects_missing_store(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_app(store_path=tmp_path / "does-not-exist.duckdb")
