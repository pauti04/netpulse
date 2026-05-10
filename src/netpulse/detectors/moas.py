"""MOAS detector: flag prefixes with more than one origin AS in the window."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from netpulse.alerts import Alert
from netpulse.detectors.base import DetectorBase
from netpulse.features.bgp import BGPWindowFeatures


@dataclass
class MOASDetector(DetectorBase[BGPWindowFeatures]):
    name: ClassVar[str] = "moas"
    min_announce_count: int = 1

    def score(self, features: BGPWindowFeatures) -> list[Alert]:
        alerts: list[Alert] = []
        for prefix, origins in features.origins_by_prefix.items():
            if len(origins) <= 1:
                continue
            announce_count = features.announce_count_by_prefix.get(prefix, 0)
            if announce_count < self.min_announce_count:
                continue
            origin_list = sorted(origins)
            alerts.append(
                Alert(
                    timestamp_us=features.window_end_us,
                    detector=self.name,
                    severity="warning",
                    entity=prefix,
                    summary=(f"announced from {len(origins)} distinct origin ASNs: {origin_list}"),
                    window_start_us=features.window_start_us,
                    window_end_us=features.window_end_us,
                    evidence={
                        "origin_asns": origin_list,
                        "announce_count": announce_count,
                    },
                )
            )
        return alerts
