"""Thread-safe shared state between the live monitor and the web surface.

The monitor thread produces detections + counters; FastAPI handlers
consume them. A single lock guards a bounded ring buffer of recent
detections plus running counters, so the whole live product is one
process with no database between writer and reader.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class Detection:
    """One anomaly the live monitor flagged, flattened for display/JSON."""

    ts_us: int
    detector: str
    severity: str
    entity: str
    summary: str


class DetectionFeed:
    """Bounded, thread-safe feed of recent detections + live counters."""

    def __init__(self, maxlen: int = 200) -> None:
        self._lock = threading.Lock()
        self._buf: deque[Detection] = deque(maxlen=maxlen)
        self._start_monotonic = time.monotonic()
        self.updates_seen = 0
        self.windows_evaluated = 0
        self.reconnects = 0
        self.detections_total = 0
        self.last_update_ts_us = 0
        self.connected = False

    # ---- producer side (monitor thread) ----

    def note_updates(self, n: int, last_ts_us: int) -> None:
        with self._lock:
            self.updates_seen += n
            if last_ts_us > self.last_update_ts_us:
                self.last_update_ts_us = last_ts_us

    def note_window(self) -> None:
        with self._lock:
            self.windows_evaluated += 1

    def note_reconnect(self) -> None:
        with self._lock:
            self.reconnects += 1

    def set_connected(self, value: bool) -> None:
        with self._lock:
            self.connected = value

    def add(self, detections: list[Detection]) -> None:
        if not detections:
            return
        with self._lock:
            self._buf.extend(detections)
            self.detections_total += len(detections)

    # ---- consumer side (web handlers) ----

    def recent(self, limit: int = 50) -> list[Detection]:
        with self._lock:
            items = list(self._buf)
        # newest first
        items.reverse()
        return items[:limit]

    def stats(self) -> dict[str, object]:
        with self._lock:
            return {
                "connected": self.connected,
                "uptime_seconds": int(time.monotonic() - self._start_monotonic),
                "updates_seen": self.updates_seen,
                "windows_evaluated": self.windows_evaluated,
                "reconnects": self.reconnects,
                "detections_total": self.detections_total,
                "buffered": len(self._buf),
                "last_update_ts_us": self.last_update_ts_us,
            }
