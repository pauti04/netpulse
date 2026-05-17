"""Active DNS probe ingestor using ``dnspython``.

Pulls real DNS responses from configured resolvers for a configured
set of hostnames and writes them as :class:`DNSProbeRecord` rows. No
external API surface is imagined here — dnspython's
``dns.resolver.Resolver`` is the only external dependency, and its
output shape is the standard ``dns.resolver.Answer`` /
``dns.exception.DNSException`` set documented in the dnspython
project.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import dns.exception
import dns.resolver

from netpulse.storage.dns_schema import DNSProbeRecord
from netpulse.storage.dns_store import DNSProbeStore


def _classify_exception(exc: dns.exception.DNSException) -> str:
    """Map a dnspython exception to one of NetPulse's short error tags."""
    name = type(exc).__name__
    if name == "NXDOMAIN":
        return "NXDOMAIN"
    if name in {"NoAnswer", "NoNameservers"}:
        return "NOANSWER"
    if name == "Timeout":
        return "TIMEOUT"
    if name == "YXDOMAIN":
        return "YXDOMAIN"
    return "OTHER"


def probe_once(
    hostname: str,
    resolver_ip: str,
    qtype: str = "A",
    timeout_s: float = 2.0,
    now_us: int | None = None,
) -> DNSProbeRecord:
    """Send one query, return the probe record. Never raises."""
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = [resolver_ip]
    r.timeout = timeout_s
    r.lifetime = timeout_s * 1.5

    start_ns = time.perf_counter_ns()
    ts_us = int(time.time() * 1_000_000) if now_us is None else now_us
    try:
        r.resolve(hostname, qtype)
        elapsed_us = (time.perf_counter_ns() - start_ns) // 1000
        return DNSProbeRecord(
            timestamp_us=ts_us,
            hostname=hostname,
            resolver_ip=resolver_ip,
            qtype=qtype,
            success=True,
            response_us=int(elapsed_us),
            error=None,
        )
    except dns.exception.DNSException as e:
        elapsed_us = (time.perf_counter_ns() - start_ns) // 1000
        return DNSProbeRecord(
            timestamp_us=ts_us,
            hostname=hostname,
            resolver_ip=resolver_ip,
            qtype=qtype,
            success=False,
            response_us=int(elapsed_us),
            error=_classify_exception(e),
        )


def run_probe_loop(
    store: DNSProbeStore,
    hostnames: Sequence[str],
    resolvers: Sequence[str],
    interval_s: float,
    duration_s: float,
    qtype: str = "A",
    timeout_s: float = 2.0,
) -> int:
    """Loop: every ``interval_s`` for ``duration_s`` total, probe each
    (hostname, resolver) pair and write the result. Returns the total
    number of records written.

    Blocks the calling thread; suitable for a CLI invocation. The probe
    of each pair is sequential — for tens of hostnames at a per-minute
    interval the overhead is negligible.
    """
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")
    end_at = time.monotonic() + duration_s
    n_written = 0
    while True:
        batch: list[DNSProbeRecord] = []
        for h in hostnames:
            for rip in resolvers:
                batch.append(probe_once(h, rip, qtype=qtype, timeout_s=timeout_s))
        n_written += store.write_batch(batch)
        remaining = end_at - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval_s, max(0.01, remaining)))
    return n_written
