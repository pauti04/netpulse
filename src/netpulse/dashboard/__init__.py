"""Streamlit dashboard over the alert-history DuckDB.

The dashboard is split in two:

- ``data.py`` — pure-Python data layer that reads the alert history DB
  and shapes it for the UI. No Streamlit imports, fully unit-testable.
- ``app.py`` — Streamlit UI. Importable but only renders when invoked
  via ``streamlit run`` or the ``netpulse dashboard`` CLI command.

This split lets us unit-test the aggregation logic without a Streamlit
runtime, and keeps the UI thin (just calls into the data layer).
"""

from netpulse.dashboard.data import (
    AlertSummary,
    DetectorBreakdown,
    SeverityBreakdown,
    TimeBucket,
    load_alerts,
    summarize_window,
)

__all__ = [
    "AlertSummary",
    "DetectorBreakdown",
    "SeverityBreakdown",
    "TimeBucket",
    "load_alerts",
    "summarize_window",
]
