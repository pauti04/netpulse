"""DNS reachability detector: flag elevated DNS-resolution failure rates.

Consumes the per-hostname stats produced by
:func:`netpulse.features.dns.extract_dns_features` and emits one alert
per hostname that crosses the failure-rate threshold within the
window. A minimum probe count guards against single-probe flakes.

This is intentionally a *generic* DNS-reachability signal — it
captures the case where a name fails to resolve at a meaningful share
of attempts. It does not try to distinguish NXDOMAIN from SERVFAIL
from TIMEOUT; the underlying probe records preserve that distinction
for later analysis, but the alert is "this hostname is unreachable
right now" at a single threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from netpulse.alerts import Alert
from netpulse.detectors.base import DetectorBase
from netpulse.features.dns import DNSWindowFeatures


@dataclass
class DNSFailureRateDetector(DetectorBase[DNSWindowFeatures]):
    """Flag per-hostname DNS failure rates above a threshold."""

    name: ClassVar[str] = "dns_failure_rate"
    failure_rate_threshold: float = 0.50
    min_probes: int = 4

    def score(self, features: DNSWindowFeatures) -> list[Alert]:
        alerts: list[Alert] = []
        for hostname, stats in features.by_hostname.items():
            if stats.n_total < self.min_probes:
                continue
            if stats.failure_rate < self.failure_rate_threshold:
                continue
            alerts.append(
                Alert(
                    timestamp_us=features.window_end_us,
                    detector=self.name,
                    severity="critical" if stats.failure_rate >= 0.9 else "warning",
                    entity=hostname,
                    summary=(
                        f"DNS resolution failed for {hostname}: "
                        f"{stats.n_failure}/{stats.n_total} probes "
                        f"({stats.failure_rate:.1%}) returned an error"
                    ),
                    window_start_us=features.window_start_us,
                    window_end_us=features.window_end_us,
                    evidence={
                        "hostname": hostname,
                        "n_total": stats.n_total,
                        "n_failure": stats.n_failure,
                        "failure_rate": stats.failure_rate,
                        "threshold": self.failure_rate_threshold,
                    },
                )
            )
        return alerts
