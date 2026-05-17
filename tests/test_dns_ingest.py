"""Unit tests for the DNS probe ingestor.

The real ``dns.resolver.Resolver.resolve`` is patched so we never hit
the network — but the dnspython exception types and error-tag mapping
are exercised end-to-end.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import dns.exception
import dns.resolver

from netpulse.ingest.dns import _classify_exception, probe_once, run_probe_loop
from netpulse.storage.dns_store import DNSProbeStore


def test_classify_exception_maps_common_dnspython_errors() -> None:
    assert _classify_exception(dns.resolver.NXDOMAIN()) == "NXDOMAIN"
    assert _classify_exception(dns.exception.Timeout()) == "TIMEOUT"
    assert _classify_exception(dns.resolver.NoAnswer()) == "NOANSWER"
    assert _classify_exception(dns.resolver.NoNameservers()) == "NOANSWER"
    assert _classify_exception(dns.exception.DNSException()) == "OTHER"


def test_probe_once_records_success() -> None:
    with patch.object(dns.resolver.Resolver, "resolve", return_value=None):
        r = probe_once("example.com", "1.1.1.1", now_us=1_700_000_000_000_000)
    assert r.success is True
    assert r.error is None
    assert r.hostname == "example.com"
    assert r.resolver_ip == "1.1.1.1"
    assert r.qtype == "A"
    assert r.timestamp_us == 1_700_000_000_000_000


def test_probe_once_records_nxdomain_failure() -> None:
    with patch.object(dns.resolver.Resolver, "resolve", side_effect=dns.resolver.NXDOMAIN()):
        r = probe_once("nonexistent.example", "1.1.1.1", now_us=1_700_000_000_000_000)
    assert r.success is False
    assert r.error == "NXDOMAIN"


def test_run_probe_loop_writes_one_round_per_pair(tmp_path: Path) -> None:
    store_path = tmp_path / "dns.duckdb"
    with (
        patch.object(dns.resolver.Resolver, "resolve", return_value=None),
        DNSProbeStore(store_path) as s,
    ):
        # duration_s=0 means: do one round and exit immediately.
        written = run_probe_loop(
            s,
            hostnames=["a.example", "b.example", "c.example"],
            resolvers=["1.1.1.1", "8.8.8.8"],
            interval_s=0.01,
            duration_s=0.0,
        )
        assert written == 6
        assert s.count() == 6
