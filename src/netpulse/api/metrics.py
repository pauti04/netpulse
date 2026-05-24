"""Prometheus-format metrics for the NetPulse FastAPI surface.

Tiny, no external dependency. Exposes a handful of counters and gauges
that match what an operator would graph: request counts per endpoint,
alerts emitted per detector, alerts persisted, RPKI VRP count, plus
per-endpoint request-duration histograms.

Format spec: https://prometheus.io/docs/instrumenting/exposition_formats/
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# Default histogram buckets in seconds. Tuned for HTTP-handler latency
# at NetPulse's scale: most calls finish in tens of milliseconds; the
# heaviest (sub-prefix detect with a fat baseline) sits in the hundreds
# of ms range; anything above 5s is a clear regression.
DEFAULT_BUCKETS: tuple[float, ...] = (
    0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)


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


@dataclass
class _Histogram:
    """Per-label-value bucketed histogram.

    Each ``label_value`` (typically an endpoint name like ``detect_bgp``)
    maintains its own bucket counts, sum-of-observations, and total
    count. Used to graph per-endpoint p50/p95/p99 latency in Grafana
    via Prometheus' ``histogram_quantile``.
    """

    name: str
    help_text: str
    buckets: tuple[float, ...] = DEFAULT_BUCKETS
    # label_value -> (bucket_counts, sum_seconds, count). Bucket counts
    # are cumulative ("le") as Prometheus expects.
    series: dict[str, tuple[list[int], float, int]] = field(default_factory=dict)

    def observe(self, value: float, label_value: str = "_") -> None:
        bucket_counts, total, count = self.series.get(
            label_value, ([0] * len(self.buckets), 0.0, 0)
        )
        for i, upper in enumerate(self.buckets):
            if value <= upper:
                bucket_counts[i] += 1
        self.series[label_value] = (bucket_counts, total + value, count + 1)


class MetricsRegistry:
    """Tiny in-process metrics registry; thread-safe via a single lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, _Counter] = {}
        self._gauges: dict[str, _Gauge] = {}
        self._histograms: dict[str, _Histogram] = {}

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

    def histogram(
        self,
        name: str,
        help_text: str,
        buckets: tuple[float, ...] = DEFAULT_BUCKETS,
    ) -> _Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = _Histogram(
                    name=name, help_text=help_text, buckets=buckets
                )
            return self._histograms[name]

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
            for h in self._histograms.values():
                lines.append(f"# HELP {h.name} {h.help_text}")
                lines.append(f"# TYPE {h.name} histogram")
                for label_value, (counts, total, n) in sorted(h.series.items()):
                    ev = label_value.replace("\\", "\\\\").replace('"', '\\"')
                    for i, upper in enumerate(h.buckets):
                        lines.append(
                            f'{h.name}_bucket{{endpoint="{ev}",le="{upper}"}} {counts[i]}'
                        )
                    lines.append(
                        f'{h.name}_bucket{{endpoint="{ev}",le="+Inf"}} {n}'
                    )
                    lines.append(f'{h.name}_sum{{endpoint="{ev}"}} {total}')
                    lines.append(f'{h.name}_count{{endpoint="{ev}"}} {n}')
        return "\n".join(lines) + "\n"
