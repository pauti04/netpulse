"""Multi-signal fusion: correlate BGP anomalies with RIPE Atlas latency.

A standalone BGP alert says "the routing table changed in a suspicious
way." A standalone Atlas latency spike says "users near these probes saw
slower paths." Either alone is noisy. *Both at the same time* is a much
stronger signal that something operationally bad happened.

This module provides a small correlator: given a window's BGP alerts,
a baseline-window Atlas latency, and a same-window Atlas latency, it
emits a single fused alert when both signals fire and the latency
exceeds a configurable jump factor over the baseline.

It does not try to attribute *which* BGP anomaly caused the latency
change -- that requires more topology knowledge than the project
currently has. It just correlates the two by time window.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from netpulse.alerts import Alert


@dataclass
class MultiSignalCorrelator:
    """Cross-correlate BGP alerts with an Atlas latency-anomaly signal."""

    # Latency is "elevated" when the window median RTT exceeds the
    # baseline median RTT by this multiplicative factor.
    rtt_jump_factor: float = 1.15

    def fuse(
        self,
        bgp_alerts: Sequence[Alert],
        window_start_us: int,
        window_end_us: int,
        atlas_baseline_median_rtt_ms: float,
        atlas_window_median_rtt_ms: float,
        atlas_msm_id: int | None = None,
        atlas_target: str | None = None,
        dns_alerts: Sequence[Alert] | None = None,
    ) -> list[Alert]:
        """Return a fused alert list (0 or 1 Alert) for one window.

        Returns empty if no BGP alerts fired, if the baseline RTT is
        non-positive (no comparison possible), or if the window RTT is
        not elevated above the baseline by ``rtt_jump_factor``.

        ``dns_alerts`` is the optional third axis. When provided and
        non-empty, the fused alert's severity is *escalated* to critical
        and the evidence is annotated with the DNS-failure hostnames
        observed in the same window. Absence of DNS alerts does not
        suppress the fusion — BGP + Atlas alone still fires.
        """
        if not bgp_alerts:
            return []
        if atlas_baseline_median_rtt_ms <= 0:
            return []
        ratio = atlas_window_median_rtt_ms / atlas_baseline_median_rtt_ms
        if ratio < self.rtt_jump_factor:
            return []

        bgp_detectors = sorted({a.detector for a in bgp_alerts})
        dns_alerts = dns_alerts or []
        dns_hostnames = sorted({a.entity for a in dns_alerts})

        summary_tail = ""
        if dns_hostnames:
            summary_tail = (
                f"; also {len(dns_alerts)} DNS-failure alert(s) on {len(dns_hostnames)} hostname(s)"
            )

        return [
            Alert(
                timestamp_us=window_end_us,
                detector="multi_signal_fusion",
                severity="critical",
                entity=(f"msm:{atlas_msm_id}" if atlas_msm_id is not None else "atlas"),
                summary=(
                    f"BGP anomaly ({len(bgp_alerts)} alerts from "
                    f"{bgp_detectors}) co-occurred with Atlas median-RTT "
                    f"jump from {atlas_baseline_median_rtt_ms:.1f}ms to "
                    f"{atlas_window_median_rtt_ms:.1f}ms ({ratio:.2f}x)"
                    f"{summary_tail}"
                ),
                window_start_us=window_start_us,
                window_end_us=window_end_us,
                evidence={
                    "n_bgp_alerts": len(bgp_alerts),
                    "bgp_alert_detectors": bgp_detectors,
                    "atlas_msm_id": atlas_msm_id,
                    "atlas_target": atlas_target,
                    "atlas_baseline_median_rtt_ms": atlas_baseline_median_rtt_ms,
                    "atlas_window_median_rtt_ms": atlas_window_median_rtt_ms,
                    "rtt_jump_factor": ratio,
                    "rtt_threshold_factor": self.rtt_jump_factor,
                    "n_dns_alerts": len(dns_alerts),
                    "dns_failure_hostnames": dns_hostnames,
                },
            )
        ]
