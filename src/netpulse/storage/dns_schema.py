"""Schema for active-DNS-probe results.

A single DNS probe record captures one query attempt: was the response
received, how long did it take, and what error (if any) came back.
The schema is intentionally local — it's the output of NetPulse's own
``dnspython``-based probe loop, *not* a transformation of any external
JSON shape. Atlas DNS measurement integration is a future signal and
will not write to this table.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DNSProbeRecord:
    """One DNS query attempt against one resolver.

    Microseconds since Unix epoch (UTC) for ``timestamp_us``.
    ``response_us`` is the elapsed time from query start to response or
    timeout, in microseconds. ``error`` is None for a successful
    resolution, otherwise a short error tag (``NXDOMAIN``, ``TIMEOUT``,
    ``SERVFAIL``, ``REFUSED``, ``OTHER``).
    """

    timestamp_us: int
    hostname: str
    resolver_ip: str
    qtype: str  # "A" / "AAAA" / etc.
    success: bool
    response_us: int
    error: str | None = None


DNS_PROBES_TABLE = "dns_probes"


CREATE_DNS_PROBES_TABLE = f"""
CREATE TABLE IF NOT EXISTS {DNS_PROBES_TABLE} (
    timestamp_us BIGINT  NOT NULL,
    hostname     VARCHAR NOT NULL,
    resolver_ip  VARCHAR NOT NULL,
    qtype        VARCHAR NOT NULL,
    success      BOOLEAN NOT NULL,
    response_us  BIGINT  NOT NULL,
    error        VARCHAR
);
"""


INSERT_DNS_PROBE = f"""
INSERT INTO {DNS_PROBES_TABLE}
    (timestamp_us, hostname, resolver_ip, qtype, success, response_us, error)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def dns_probe_to_row(
    r: DNSProbeRecord,
) -> tuple[int, str, str, str, bool, int, str | None]:
    return (
        r.timestamp_us,
        r.hostname,
        r.resolver_ip,
        r.qtype,
        r.success,
        r.response_us,
        r.error,
    )
