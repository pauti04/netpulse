"""Historical replay harness: score detectors against labeled incidents."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from netpulse.alerts import Alert
from netpulse.benchmark.incident import Incident
from netpulse.detectors.base import DetectorBase
from netpulse.features.bgp import BGPWindowFeatures, extract_bgp_features
from netpulse.storage.duckdb_store import BGPStore


@dataclass(slots=True)
class ReplayResult:
    """Outcome of replaying a single incident through a set of BGP detectors."""

    incident_id: str
    detected: bool
    latency_us: int | None
    alerts: list[Alert] = field(default_factory=list)


def replay_bgp_incident(
    incident: Incident,
    store: BGPStore,
    detectors: Sequence[DetectorBase[BGPWindowFeatures]],
    chunk_us: int = 60_000_000,
) -> ReplayResult:
    """Replay the incident and return first-detection latency + final alerts.

    Each step queries an expanding window ``[start_us, chunk_end)`` so latency
    reflects what a streaming detector would have seen as records arrived in
    order. Reported alerts are extracted once over the full incident window.
    """
    if chunk_us <= 0:
        raise ValueError("chunk_us must be positive")

    def _matches(alert: Alert) -> bool:
        return incident.prefix is None or alert.entity == incident.prefix

    first_match_time_us: int | None = None
    cursor = incident.start_us
    while cursor < incident.end_us and first_match_time_us is None:
        chunk_end = min(cursor + chunk_us, incident.end_us)
        features = extract_bgp_features(store, incident.start_us, chunk_end)
        for det in detectors:
            if any(_matches(a) for a in det.score(features)):
                first_match_time_us = chunk_end
                break
        cursor = chunk_end

    full_features = extract_bgp_features(store, incident.start_us, incident.end_us)
    captured: list[Alert] = []
    for det in detectors:
        captured.extend(det.score(full_features))

    reference_us = incident.onset_us if incident.onset_us is not None else incident.start_us
    latency_us = first_match_time_us - reference_us if first_match_time_us is not None else None

    return ReplayResult(
        incident_id=incident.id,
        detected=first_match_time_us is not None,
        latency_us=latency_us,
        alerts=captured,
    )
