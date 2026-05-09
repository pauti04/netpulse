"""Alert dataclass and severity types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["info", "warning", "critical"]


@dataclass(slots=True)
class Alert:
    """A single detector finding.

    Timestamps are microseconds since the Unix epoch, UTC.
    """

    timestamp_us: int
    detector: str
    severity: Severity
    entity: str
    summary: str
    window_start_us: int
    window_end_us: int
    evidence: dict[str, Any] = field(default_factory=dict)


__all__ = ["Alert", "Severity"]
