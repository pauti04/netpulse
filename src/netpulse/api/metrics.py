"""Prometheus-format metrics for the NetPulse FastAPI surface.

Tiny, no external dependency. Exposes a handful of counters and gauges
that match what an operator would graph: request counts per endpoint,
alerts emitted per detector, alerts persisted, RPKI VRP count.

Format spec: https://prometheus.io/docs/instrumenting/exposition_formats/
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class _Counter:
    name: str
    help_text: str
    value: int = 0
    labels: dict[str, int] = field(default_factory=dict)

    def inc(self, n: int = 1, label_value: str | None = None) -> None:
        if label_value is not None:
            self.labels[label_value] = self.labels.get(label_value, 0) + n
        else:
            self.value += n


@dataclass
class _Gauge:
    name: str
    help_text: str
    value: float = 0.0

    def set(self, value: float) -> None:
        self.value = value


class MetricsRegistry:
    """Tiny in-process metrics registry; thread-safe via a single lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, _Counter] = {}
        self._gauges: dict[str, _Gauge] = {}

    def counter(self, name: str, help_text: str) -> _Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = _Counter(name=name, help_text=help_text)
            return self._counters[name]

    def gauge(self, name: str, help_text: str) -> _Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = _Gauge(name=name, help_text=help_text)
            return self._gauges[name]

    def render(self) -> str:
        """Return the registry's content in Prometheus text-exposition format."""
        lines: list[str] = []
        with self._lock:
            for c in self._counters.values():
                lines.append(f"# HELP {c.name} {c.help_text}")
                lines.append(f"# TYPE {c.name} counter")
                if c.labels:
                    for label_value, count in sorted(c.labels.items()):
                        # Escape only the obvious specials in label values.
                        ev = label_value.replace("\\", "\\\\").replace('"', '\\"')
                        lines.append(f'{c.name}{{detector="{ev}"}} {count}')
                else:
                    lines.append(f"{c.name} {c.value}")
            for g in self._gauges.values():
                lines.append(f"# HELP {g.name} {g.help_text}")
                lines.append(f"# TYPE {g.name} gauge")
                lines.append(f"{g.name} {g.value}")
        return "\n".join(lines) + "\n"
