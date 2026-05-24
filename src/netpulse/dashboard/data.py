"""Pure-Python data layer for the Streamlit dashboard.

Reads from an existing ``AlertHistoryStore`` DuckDB and reshapes rows
into the aggregates the UI needs:

- timeline buckets (count per N-minute bucket, optionally faceted by detector)
- detector + severity breakdowns
- a simple high-level summary for the top of the page

No Streamlit, pandas, or plotting imports — that keeps the data layer
cheap to unit-test and lets the UI stay a thin wrapper.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from netpulse.alerts import Alert
from netpulse.alerts.store import AlertHistoryStore


@dataclass(frozen=True, slots=True)
class TimeBucket:
    """One bucket on the alerts-over-time chart."""

    bucket_start_us: int
    bucket_end_us: int
    count: int


@dataclass(frozen=True, slots=True)
class DetectorBreakdown:
    detector: str
    count: int


@dataclass(frozen=True, slots=True)
class SeverityBreakdown:
    severity: str
    count: int


@dataclass(frozen=True, slots=True)
class AlertSummary:
    """Top-of-page summary stats."""

    total: int
    first_us: int | None
    last_us: int | None
    by_detector: list[DetectorBreakdown]
    by_severity: list[SeverityBreakdown]
    top_entities: list[tuple[str, int]]


def load_alerts(
    history_path: Path,
    since_us: int,
    until_us: int,
    detector: str | None = None,
    severity: str | None = None,
    limit: int = 10_000,
) -> list[Alert]:
    """Read alerts in ``[since_us, until_us)`` from the history store.

    Thin wrapper around ``AlertHistoryStore.query_window``; exists so
    the UI can call into a single function and the test suite can
    parameterize easily.
    """
    with AlertHistoryStore(history_path) as hist:
        return hist.query_window(
            since_us=since_us,
            until_us=until_us,
            detector=detector,
            severity=severity,
            limit=limit,
        )


def bucketize(
    alerts: Sequence[Alert],
    bucket_size_us: int,
    window_start_us: int,
    window_end_us: int,
) -> list[TimeBucket]:
    """Group alerts into uniform time buckets across the window.

    Buckets at the edges are right-open: ``[start, start+bucket_size)``.
    Empty buckets are emitted so the UI's bar chart has continuous
    x-axis coverage.
    """
    if bucket_size_us <= 0:
        raise ValueError("bucket_size_us must be positive")
    if window_end_us <= window_start_us:
        raise ValueError("window_end_us must be greater than window_start_us")

    n_buckets = (window_end_us - window_start_us + bucket_size_us - 1) // bucket_size_us
    counts = [0] * n_buckets
    for a in alerts:
        if a.timestamp_us < window_start_us or a.timestamp_us >= window_end_us:
            continue
        idx = (a.timestamp_us - window_start_us) // bucket_size_us
        if 0 <= idx < n_buckets:
            counts[idx] += 1

    return [
        TimeBucket(
            bucket_start_us=window_start_us + i * bucket_size_us,
            bucket_end_us=min(window_start_us + (i + 1) * bucket_size_us, window_end_us),
            count=counts[i],
        )
        for i in range(n_buckets)
    ]


def summarize_window(alerts: Sequence[Alert], top_n_entities: int = 5) -> AlertSummary:
    """Top-of-page summary statistics for the loaded alert set."""
    if not alerts:
        return AlertSummary(
            total=0,
            first_us=None,
            last_us=None,
            by_detector=[],
            by_severity=[],
            top_entities=[],
        )

    by_det: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    by_ent: dict[str, int] = {}
    first_us = alerts[0].timestamp_us
    last_us = alerts[0].timestamp_us
    for a in alerts:
        by_det[a.detector] = by_det.get(a.detector, 0) + 1
        by_sev[a.severity] = by_sev.get(a.severity, 0) + 1
        by_ent[a.entity] = by_ent.get(a.entity, 0) + 1
        if a.timestamp_us < first_us:
            first_us = a.timestamp_us
        if a.timestamp_us > last_us:
            last_us = a.timestamp_us

    det_sorted = sorted(by_det.items(), key=lambda kv: (-kv[1], kv[0]))
    sev_sorted = sorted(by_sev.items(), key=lambda kv: (-kv[1], kv[0]))
    ent_sorted = sorted(by_ent.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n_entities]

    return AlertSummary(
        total=len(alerts),
        first_us=first_us,
        last_us=last_us,
        by_detector=[DetectorBreakdown(d, c) for d, c in det_sorted],
        by_severity=[SeverityBreakdown(s, c) for s, c in sev_sorted],
        top_entities=ent_sorted,
    )
