"""DNS reachability feature extraction over a time window.

Aggregates :class:`netpulse.storage.dns_schema.DNSProbeRecord` rows in
a half-open ``[start_us, end_us)`` window into per-hostname success
counts, error counts, and response-time statistics. The detector
consumes these features rather than raw rows so the per-hostname
threshold checks are O(distinct-hostname) instead of O(records).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from netpulse.storage.dns_store import DNSProbeStore


@dataclass(slots=True)
class DNSHostnameStats:
    """Per-hostname aggregate over the window."""

    n_total: int = 0
    n_success: int = 0
    n_failure: int = 0
    response_us_samples: list[int] = field(default_factory=list)

    @property
    def failure_rate(self) -> float:
        return 0.0 if self.n_total == 0 else self.n_failure / self.n_total

    @property
    def median_response_us(self) -> int | None:
        if not self.response_us_samples:
            return None
        return int(median(self.response_us_samples))


@dataclass(slots=True)
class DNSWindowFeatures:
    """Aggregate features over a half-open ``[start_us, end_us)`` window."""

    window_start_us: int
    window_end_us: int
    by_hostname: dict[str, DNSHostnameStats] = field(default_factory=dict)

    @property
    def n_total(self) -> int:
        return sum(s.n_total for s in self.by_hostname.values())

    @property
    def n_failure(self) -> int:
        return sum(s.n_failure for s in self.by_hostname.values())

    @property
    def overall_failure_rate(self) -> float:
        return 0.0 if self.n_total == 0 else self.n_failure / self.n_total


def extract_dns_features(
    store: DNSProbeStore,
    start_us: int,
    end_us: int,
) -> DNSWindowFeatures:
    """Aggregate DNS probe results in the window into per-hostname stats."""
    if end_us <= start_us:
        raise ValueError("end_us must be greater than start_us")

    rows = store.query(
        """
        SELECT hostname, success, response_us
        FROM dns_probes
        WHERE timestamp_us >= ? AND timestamp_us < ?
        """,
        [start_us, end_us],
    )

    feats = DNSWindowFeatures(window_start_us=start_us, window_end_us=end_us)
    for hostname_raw, success_raw, response_us_raw in rows:
        hostname = str(hostname_raw)
        success = bool(success_raw)
        response_us = int(response_us_raw)
        s = feats.by_hostname.setdefault(hostname, DNSHostnameStats())
        s.n_total += 1
        if success:
            s.n_success += 1
            s.response_us_samples.append(response_us)
        else:
            s.n_failure += 1
    return feats
