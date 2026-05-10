"""Cooldown-based alert deduplication.

Stream and replay both re-evaluate detectors on every interval, so the
same alert (same detector + same entity + same severity) fires repeatedly
while the underlying anomaly persists. This is operational noise; once
the alert is acknowledged or the situation is stable, the operator does
not need a duplicate every 10 seconds.

The deduper keeps a fingerprint -> last-emitted-timestamp map and
suppresses re-emissions within ``cooldown_us``. The first occurrence of
each fingerprint always passes; subsequent matches within the cooldown
are dropped.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from netpulse.alerts import Alert

# 5 minutes default — a reasonable balance between "stop spamming the
# operator" and "remind them the situation is still active."
DEFAULT_COOLDOWN_US = 5 * 60 * 1_000_000


@dataclass
class AlertDeduper:
    cooldown_us: int = DEFAULT_COOLDOWN_US
    _last_seen: dict[str, int] = field(default_factory=dict)

    @staticmethod
    def fingerprint(alert: Alert) -> str:
        return f"{alert.detector}|{alert.entity}|{alert.severity}"

    def should_emit(self, alert: Alert) -> bool:
        fp = self.fingerprint(alert)
        last = self._last_seen.get(fp)
        if last is not None and alert.timestamp_us - last < self.cooldown_us:
            return False
        self._last_seen[fp] = alert.timestamp_us
        return True

    def filter(self, alerts: Iterable[Alert]) -> Iterator[Alert]:
        for a in alerts:
            if self.should_emit(a):
                yield a
