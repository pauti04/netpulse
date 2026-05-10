"""RIPE Atlas ingestion via cousteau.

API surface used (verified against measurement 1001 on 2026-05-09):
- ``ripe.atlas.cousteau.AtlasResultsRequest(msm_id, start, stop).create()``
  returns ``(is_success, list[dict])``.
- For ping measurements each result has the fields ``timestamp`` (epoch
  seconds), ``msm_id``, ``prb_id``, ``dst_addr``, ``sent``, ``rcvd``,
  ``min``, ``avg``, ``max`` (RTT in ms; -1 when all packets lost).
"""

from __future__ import annotations

from datetime import UTC, datetime

try:
    from ripe.atlas.cousteau import AtlasResultsRequest
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "ripe.atlas.cousteau is required for Atlas ingestion. "
        "Install via 'uv sync' (it is in the default dependency set)."
    ) from e

from netpulse.storage.atlas_schema import AtlasPingRecord
from netpulse.storage.atlas_store import AtlasPingStore


def _rtt_or_none(value: object) -> float | None:
    """Atlas reports -1 for "all packets lost"; normalize to None."""
    if value is None:
        return None
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    return v


def pull_atlas_ping_window(
    msm_id: int,
    start_us: int,
    end_us: int,
    store: AtlasPingStore,
) -> int:
    """Pull ping results for ``msm_id`` in ``[start_us, end_us)`` into ``store``."""
    if end_us <= start_us:
        raise ValueError("end_us must be greater than start_us")

    start = datetime.fromtimestamp(start_us / 1_000_000, tz=UTC)
    stop = datetime.fromtimestamp(end_us / 1_000_000, tz=UTC)
    is_success, results = AtlasResultsRequest(msm_id=msm_id, start=start, stop=stop).create()
    if not is_success:
        raise RuntimeError(f"Atlas request failed for msm_id={msm_id}")

    records = [
        AtlasPingRecord(
            timestamp_us=int(r["timestamp"]) * 1_000_000,
            msm_id=int(r["msm_id"]),
            prb_id=int(r["prb_id"]),
            dst_addr=str(r.get("dst_addr") or ""),
            sent=int(r.get("sent", 0)),
            rcvd=int(r.get("rcvd", 0)),
            min_rtt_ms=_rtt_or_none(r.get("min")),
            avg_rtt_ms=_rtt_or_none(r.get("avg")),
            max_rtt_ms=_rtt_or_none(r.get("max")),
        )
        for r in results
    ]
    if not records:
        return 0
    return store.write_batch(records)
