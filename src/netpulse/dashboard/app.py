"""Streamlit dashboard over the alert-history DuckDB.

Run via:

    netpulse dashboard --history alerts.duckdb [--port 8501]

The UI is intentionally thin -- all aggregation lives in
``netpulse.dashboard.data``. Streamlit's job here is to render charts
and host the filter widgets.

Charts use Streamlit's built-in ``bar_chart`` / ``line_chart`` (which
render via Altair). No pandas DataFrames flow through the data layer
to keep that layer cheap to import + test; we convert here, at the UI
boundary, where pandas is paid for anyway.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import streamlit as st  # type: ignore[import-not-found]

from netpulse import __version__
from netpulse.dashboard.data import bucketize, load_alerts, summarize_window


def _iso(us: int) -> str:
    return datetime.fromtimestamp(us / 1_000_000, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _resolve_history_path() -> Path | None:
    raw = os.environ.get("NETPULSE_DASHBOARD_HISTORY")
    if raw:
        return Path(raw)
    return None


def main() -> None:
    st.set_page_config(
        page_title="NetPulse — alert console",
        layout="wide",
    )
    st.title("NetPulse — alert console")
    st.caption(f"v{__version__} · DuckDB-backed alert history")

    history_path = _resolve_history_path()
    if history_path is None or not history_path.exists():
        st.error(
            "No alert history found. Launch the dashboard with "
            "`netpulse dashboard --history path/to/alerts.duckdb`, "
            "or set NETPULSE_DASHBOARD_HISTORY env var."
        )
        st.stop()
        return  # mypy: st.stop() raises, but it's untyped; this is unreachable.
    assert history_path is not None  # narrow for mypy

    # ----- Sidebar: window + filters -----
    st.sidebar.header("Window")
    now = datetime.now(tz=UTC).replace(microsecond=0)
    default_lookback_days = 7
    default_since = now - timedelta(days=default_lookback_days)

    since_date = st.sidebar.date_input("From", value=default_since.date())
    until_date = st.sidebar.date_input("To", value=now.date())
    since_dt = datetime.combine(since_date, datetime.min.time(), tzinfo=UTC)
    until_dt = datetime.combine(until_date, datetime.max.time(), tzinfo=UTC)
    since_us = int(since_dt.timestamp() * 1_000_000)
    until_us = int(until_dt.timestamp() * 1_000_000)

    bucket_minutes = st.sidebar.slider(
        "Bucket size (minutes)",
        min_value=1,
        max_value=240,
        value=60,
        step=1,
    )

    detector_filter = st.sidebar.text_input("Detector filter (optional)", "")
    severity_filter = st.sidebar.selectbox(
        "Severity filter",
        options=["", "info", "warning", "critical"],
        index=0,
    )
    limit = st.sidebar.number_input(
        "Row limit",
        min_value=100,
        max_value=100_000,
        value=10_000,
        step=100,
    )

    # ----- Load + summarize -----
    alerts = load_alerts(
        history_path=history_path,
        since_us=since_us,
        until_us=until_us,
        detector=detector_filter or None,
        severity=severity_filter or None,
        limit=int(limit),
    )
    summary = summarize_window(alerts)

    # ----- Headline stats -----
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Alerts in window", summary.total)
    col2.metric("Detectors firing", len(summary.by_detector))
    col3.metric(
        "First alert",
        _iso(summary.first_us) if summary.first_us is not None else "—",
    )
    col4.metric(
        "Last alert",
        _iso(summary.last_us) if summary.last_us is not None else "—",
    )

    if summary.total == 0:
        st.info("No alerts in this window. Widen the date range or clear filters.")
        st.stop()

    # ----- Timeline chart -----
    st.subheader("Alerts over time")
    buckets = bucketize(
        alerts,
        bucket_size_us=bucket_minutes * 60 * 1_000_000,
        window_start_us=since_us,
        window_end_us=until_us,
    )
    timeline_rows = {
        _iso(b.bucket_start_us): b.count for b in buckets if b.count > 0 or len(buckets) <= 200
    }
    if timeline_rows:
        st.bar_chart(timeline_rows, height=240)
    else:
        st.caption("No buckets to plot (try a smaller bucket size).")

    # ----- Breakdowns side-by-side -----
    left, right = st.columns(2)
    with left:
        st.subheader("By detector")
        st.bar_chart(
            {b.detector: b.count for b in summary.by_detector},
            height=220,
        )
    with right:
        st.subheader("By severity")
        st.bar_chart(
            {b.severity: b.count for b in summary.by_severity},
            height=220,
        )

    # ----- Top entities -----
    st.subheader("Top entities")
    if summary.top_entities:
        st.table(
            [{"entity": ent, "alerts": count} for ent, count in summary.top_entities]
        )

    # ----- Raw alert table -----
    st.subheader("Raw alerts")
    rows = [
        {
            "timestamp": _iso(a.timestamp_us),
            "detector": a.detector,
            "severity": a.severity,
            "entity": a.entity,
            "summary": a.summary,
        }
        for a in alerts[: min(500, len(alerts))]
    ]
    st.dataframe(rows, use_container_width=True, height=420)
    if len(alerts) > 500:
        st.caption(f"Showing the first 500 of {len(alerts)} alerts in window.")


if __name__ == "__main__":
    main()
