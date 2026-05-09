"""Aggregate metrics over replay results."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from netpulse.benchmark.replay import ReplayResult


@dataclass(slots=True)
class BenchmarkSummary:
    total_incidents: int
    detected_count: int
    detection_rate: float  # in [0, 1]
    mean_latency_us: float | None  # over detected incidents only
    median_latency_us: float | None


def summarize(results: Sequence[ReplayResult]) -> BenchmarkSummary:
    total = len(results)
    detected = [r for r in results if r.detected]
    detected_count = len(detected)
    rate = detected_count / total if total > 0 else 0.0

    latencies = sorted(r.latency_us for r in detected if r.latency_us is not None)
    mean_latency: float | None = None
    median_latency: float | None = None
    if latencies:
        mean_latency = sum(latencies) / len(latencies)
        mid = len(latencies) // 2
        if len(latencies) % 2 == 1:
            median_latency = float(latencies[mid])
        else:
            median_latency = (latencies[mid - 1] + latencies[mid]) / 2

    return BenchmarkSummary(
        total_incidents=total,
        detected_count=detected_count,
        detection_rate=rate,
        mean_latency_us=mean_latency,
        median_latency_us=median_latency,
    )
