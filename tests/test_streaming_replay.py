from __future__ import annotations

from pathlib import Path

from netpulse.benchmark.incident import Incident
from netpulse.benchmark.streaming_replay import replay_subprefix_streaming
from netpulse.detectors.baseline import BGPBaseline
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord


def _incident(onset_us: int, prefix: str | None = "203.0.113.0/24") -> Incident:
    return Incident(
        id="t",
        name="t",
        kind="hijack",
        start_us=0,
        end_us=10_000_000_000,
        expected_detectors=["subprefix_hijack"],
        source_url="https://example.test",
        prefix=prefix,
        onset_us=onset_us,
    )


def test_streaming_detects_first_qualifying_record(tmp_path: Path) -> None:
    baseline = BGPBaseline.build({"203.0.112.0/21": {64600}})
    store_path = tmp_path / "store.duckdb"
    with BGPStore(store_path) as store:
        store.write_batch(
            [
                BGPRecord(  # background, authorized
                    timestamp_us=1_000_000,
                    collector="rrc00",
                    peer_as=64500,
                    peer_ip="192.0.2.1",
                    prefix="203.0.114.0/24",
                    update_type="A",
                    origin_as=64600,
                    as_path="64600",
                ),
                BGPRecord(  # the hijack
                    timestamp_us=5_000_000,
                    collector="rrc00",
                    peer_as=64500,
                    peer_ip="192.0.2.1",
                    prefix="203.0.113.0/24",
                    update_type="A",
                    origin_as=64601,
                    as_path="64601",
                ),
            ]
        )

        result = replay_subprefix_streaming(_incident(onset_us=4_000_000), store, baseline)

    assert result.detected
    assert result.first_detection_record_us == 5_000_000
    assert result.latency_from_onset_us == 1_000_000  # 1s
    assert result.n_records_scanned == 2  # walked through both


def test_streaming_misses_when_no_qualifying_record(tmp_path: Path) -> None:
    baseline = BGPBaseline.build({"203.0.112.0/21": {64600}})
    store_path = tmp_path / "store.duckdb"
    with BGPStore(store_path) as store:
        store.write_batch(
            [
                BGPRecord(
                    timestamp_us=1_000_000,
                    collector="rrc00",
                    peer_as=64500,
                    peer_ip="192.0.2.1",
                    prefix="203.0.114.0/24",
                    update_type="A",
                    origin_as=64600,  # legitimate
                    as_path="64600",
                ),
            ]
        )
        result = replay_subprefix_streaming(_incident(onset_us=0), store, baseline)

    assert not result.detected
    assert result.first_detection_record_us is None
    assert result.latency_from_onset_us is None
