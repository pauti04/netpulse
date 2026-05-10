from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

IncidentKind = Literal["hijack", "leak", "outage"]


@dataclass(slots=True)
class Incident:
    """One labeled historical event the replay harness scores detectors against.

    Every field must be backed by the primary source cited in ``source_url``.
    Timestamps are microseconds since the Unix epoch, UTC.
    """

    id: str
    name: str
    kind: IncidentKind
    start_us: int
    end_us: int
    expected_detectors: list[str]
    source_url: str
    prefix: str | None = None
    attacker_asn: int | None = None
    victim_asn: int | None = None
    onset_us: int | None = None  # actual event onset, if known
    bgp_store_path: str | None = None  # optional per-incident BGP DuckDB
    baseline_path: str | None = None  # optional per-incident RIB baseline
    notes: str = ""
    verified: bool = False
    extra: dict[str, object] = field(default_factory=dict)
