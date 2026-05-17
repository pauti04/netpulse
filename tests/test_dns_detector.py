from __future__ import annotations

from pathlib import Path

from netpulse.detectors.dns_failure import DNSFailureRateDetector
from netpulse.features.dns import extract_dns_features
from netpulse.storage.dns_schema import DNSProbeRecord
from netpulse.storage.dns_store import DNSProbeStore


def _probe(
    hostname: str,
    success: bool,
    ts_us: int,
    *,
    error: str | None = None,
    resolver: str = "1.1.1.1",
    response_us: int = 10_000,
) -> DNSProbeRecord:
    return DNSProbeRecord(
        timestamp_us=ts_us,
        hostname=hostname,
        resolver_ip=resolver,
        qtype="A",
        success=success,
        response_us=response_us,
        error=error,
    )


def test_extract_features_aggregates_per_hostname(tmp_path: Path) -> None:
    store_path = tmp_path / "dns.duckdb"
    with DNSProbeStore(store_path) as s:
        s.write_batch(
            [
                _probe("a.example", True, 1_000_000, response_us=10_000),
                _probe("a.example", False, 2_000_000, error="TIMEOUT"),
                _probe("a.example", True, 3_000_000, response_us=12_000),
                _probe("b.example", True, 4_000_000, response_us=20_000),
                _probe("b.example", True, 5_000_000, response_us=22_000),
            ]
        )
        feats = extract_dns_features(s, 0, 10_000_000)

    assert feats.n_total == 5
    assert feats.n_failure == 1
    assert feats.by_hostname["a.example"].failure_rate == 1 / 3
    assert feats.by_hostname["b.example"].failure_rate == 0.0
    assert feats.by_hostname["a.example"].median_response_us == 11_000
    assert feats.by_hostname["b.example"].median_response_us == 21_000


def test_detector_fires_on_high_failure_rate(tmp_path: Path) -> None:
    store_path = tmp_path / "dns.duckdb"
    with DNSProbeStore(store_path) as s:
        # 8 failures + 2 successes = 80% failure for "down.example"
        for i in range(8):
            s.write_batch([_probe("down.example", False, 1_000_000 + i, error="TIMEOUT")])
        for i in range(2):
            s.write_batch([_probe("down.example", True, 2_000_000 + i)])
        feats = extract_dns_features(s, 0, 10_000_000)

    det = DNSFailureRateDetector(failure_rate_threshold=0.5, min_probes=4)
    alerts = det.score(feats)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.detector == "dns_failure_rate"
    assert a.entity == "down.example"
    assert a.evidence["failure_rate"] == 0.8
    assert a.severity == "warning"


def test_detector_critical_at_high_failure_rate() -> None:
    from netpulse.features.dns import DNSHostnameStats, DNSWindowFeatures

    feats = DNSWindowFeatures(window_start_us=0, window_end_us=60_000_000)
    feats.by_hostname["dead.example"] = DNSHostnameStats(n_total=10, n_failure=10)
    alerts = DNSFailureRateDetector(failure_rate_threshold=0.5).score(feats)
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"


def test_detector_silent_below_min_probes() -> None:
    from netpulse.features.dns import DNSHostnameStats, DNSWindowFeatures

    feats = DNSWindowFeatures(window_start_us=0, window_end_us=60_000_000)
    feats.by_hostname["flaky.example"] = DNSHostnameStats(n_total=2, n_failure=2)
    alerts = DNSFailureRateDetector(failure_rate_threshold=0.5, min_probes=4).score(feats)
    assert alerts == []


def test_detector_silent_when_under_threshold() -> None:
    from netpulse.features.dns import DNSHostnameStats, DNSWindowFeatures

    feats = DNSWindowFeatures(window_start_us=0, window_end_us=60_000_000)
    feats.by_hostname["mostly-ok.example"] = DNSHostnameStats(n_total=10, n_failure=2)
    alerts = DNSFailureRateDetector(failure_rate_threshold=0.5, min_probes=4).score(feats)
    assert alerts == []
