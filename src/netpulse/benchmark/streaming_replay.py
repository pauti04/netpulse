"""Streaming-mode replay benchmark.

The chunk-based replay (``netpulse benchmark replay``) reports latency
bounded by the configured ``--chunk`` size, because each chunk's
expanding window is evaluated as a unit. In a real streaming deployment
the detector evaluates each update as it arrives and fires the moment a
qualifying record is seen.

This module replays an incident in that mode: walk the records in
timestamp order, evaluate the per-record check, and report the
*microsecond-resolution* delta from incident onset to first qualifying
alert. The numerical result is the lower bound on detection latency
that a streaming deployment of the same detector could achieve.

Currently scopes to the sub-prefix hijack detector (the per-record
check is well-defined: each announce can be validated independently
against the baseline). MOAS and withdraw-spike are window-bounded by
nature and are intentionally not supported here.
"""

from __future__ import annotations

from dataclasses import dataclass

from netpulse.benchmark.incident import Incident
from netpulse.detectors.baseline import BGPBaseline
from netpulse.storage.duckdb_store import BGPStore


@dataclass(slots=True)
class StreamingReplayResult:
    incident_id: str
    detected: bool
    n_records_scanned: int
    first_detection_record_us: int | None
    latency_from_onset_us: int | None


def replay_subprefix_streaming(
    incident: Incident,
    store: BGPStore,
    baseline: BGPBaseline,
) -> StreamingReplayResult:
    """Replay the incident record-by-record against the sub-prefix detector.

    For each announcement in time order, perform the sub-prefix check
    (is observed origin authorized for the prefix or its most-specific
    supernet?). Stop at the first violation. Returns the timestamp of
    the triggering record and the latency from incident.onset_us.
    """
    rows = store.query(
        "SELECT timestamp_us, prefix, origin_as FROM bgp_records "
        "WHERE update_type = 'A' AND origin_as IS NOT NULL "
        "  AND timestamp_us >= ? AND timestamp_us < ? "
        "ORDER BY timestamp_us",
        [incident.start_us, incident.end_us],
    )

    n_scanned = 0
    first_us: int | None = None
    for ts, prefix, origin_as in rows:
        n_scanned += 1
        prefix_s = str(prefix)
        oas = int(origin_as)

        # Per-record sub-prefix check, mirrors SubPrefixHijackDetector logic.
        authorized = baseline.origins_for(prefix_s)
        if authorized:
            if oas in authorized:
                continue
            # Exact-prefix mismatch
            if incident.prefix is None or prefix_s == incident.prefix:
                first_us = int(ts)
                break
            continue

        cover = baseline.most_specific_supernet(prefix_s)
        if cover is None:
            continue
        _, legitimate = cover
        if oas in legitimate:
            continue
        # Sub-prefix mismatch on an uncovered prefix.
        if incident.prefix is None or prefix_s == incident.prefix:
            first_us = int(ts)
            break

    reference_us = incident.onset_us if incident.onset_us is not None else incident.start_us
    latency = first_us - reference_us if first_us is not None else None
    return StreamingReplayResult(
        incident_id=incident.id,
        detected=first_us is not None,
        n_records_scanned=n_scanned,
        first_detection_record_us=first_us,
        latency_from_onset_us=latency,
    )
