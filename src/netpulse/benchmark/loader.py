"""Load Incident records from JSON files on disk."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

from netpulse.benchmark.incident import Incident, IncidentKind

_REQUIRED_FIELDS = (
    "id",
    "name",
    "kind",
    "start_iso",
    "end_iso",
    "expected_detectors",
    "source_url",
)


def _iso_to_us(value: str) -> int:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000)


def _incident_from_dict(payload: dict[str, Any], origin: Path) -> Incident:
    missing = [f for f in _REQUIRED_FIELDS if f not in payload]
    if missing:
        raise ValueError(f"{origin}: missing required fields {missing}")

    kind = payload["kind"]
    if kind not in get_args(IncidentKind):
        raise ValueError(f"{origin}: kind {kind!r} must be one of {list(get_args(IncidentKind))}")

    start_us = _iso_to_us(payload["start_iso"])
    end_us = _iso_to_us(payload["end_iso"])
    if end_us <= start_us:
        raise ValueError(f"{origin}: end_iso must be after start_iso")

    onset_us: int | None = None
    if "onset_iso" in payload and payload["onset_iso"] is not None:
        onset_us = _iso_to_us(str(payload["onset_iso"]))
        if not (start_us <= onset_us < end_us):
            raise ValueError(f"{origin}: onset_iso must lie within [start_iso, end_iso)")

    extra = {
        k: v
        for k, v in payload.items()
        if k
        not in {
            *_REQUIRED_FIELDS,
            "prefix",
            "attacker_asn",
            "victim_asn",
            "onset_iso",
            "bgp_store_path",
            "baseline_path",
            "notes",
            "verified",
        }
    }

    return Incident(
        id=str(payload["id"]),
        name=str(payload["name"]),
        kind=kind,
        start_us=start_us,
        end_us=end_us,
        expected_detectors=list(payload["expected_detectors"]),
        source_url=str(payload["source_url"]),
        prefix=payload.get("prefix"),
        attacker_asn=payload.get("attacker_asn"),
        victim_asn=payload.get("victim_asn"),
        onset_us=onset_us,
        bgp_store_path=payload.get("bgp_store_path"),
        baseline_path=payload.get("baseline_path"),
        notes=str(payload.get("notes", "")),
        verified=bool(payload.get("verified", False)),
        extra=extra,
    )


def load_incident(path: Path) -> Incident:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: incident JSON must be an object")
    return _incident_from_dict(payload, path)


def load_incidents(directory: Path) -> list[Incident]:
    """Load every ``*.json`` file in ``directory`` (skipping names starting with ``_``)."""
    files: Iterable[Path] = sorted(directory.glob("*.json"))
    incidents: list[Incident] = []
    for path in files:
        if path.name.startswith("_"):
            continue
        incidents.append(load_incident(path))
    return incidents
