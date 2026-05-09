"""Tests for the BGP ingest pipeline.

The integration test below pulls real data from a public RIPE RIS collector
and is therefore marked ``integration``. It is skipped by the default test
run (see pytest config in pyproject.toml). Run it explicitly with::

    uv run pytest -m integration tests/test_ingest_bgp.py
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest


@pytest.mark.integration
def test_pull_bgp_window_writes_real_records(tmp_path: Path) -> None:
    # Importing inside the test so the suite can be collected without
    # libBGPStream installed (the module raises at import time otherwise).
    from netpulse.ingest.bgp import pull_bgp_window
    from netpulse.storage.duckdb_store import BGPStore

    # 5-minute window, well in the past so the archive is settled.
    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    start_us = int(start.timestamp() * 1_000_000)
    end_us = start_us + 5 * 60 * 1_000_000

    with BGPStore(tmp_path / "bgp.duckdb") as store:
        count = pull_bgp_window("rrc00", start_us, end_us, store)
        assert count > 0
        assert store.count() == count
