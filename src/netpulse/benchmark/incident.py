"""Incident dataclass: a labeled historical event the replay harness scores against."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

IncidentKind = Literal["hijack", "leak", "outage"]


@dataclass(slots=True)
class Incident:
    """A labeled historical event used to score detectors.

    Timestamps are microseconds since the Unix epoch, UTC. Per project rule,
    all fields here must be backed by a primary source cited in
    ``source_url``; no fabricated AS numbers, prefixes, or timestamps.
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
    notes: str = ""
    verified: bool = False
    extra: dict[str, object] = field(default_factory=dict)
