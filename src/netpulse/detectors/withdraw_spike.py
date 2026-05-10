"""Withdraw-spike detector: flag windows where many prefixes go silent.

A single prefix flapping is operational noise; many distinct prefixes
withdrawing without a re-announce in the same window is an outage
signature (peer disconnect, fiber cut, BGP session reset upstream).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from netpulse.alerts import Alert
from netpulse.detectors.base import DetectorBase
from netpulse.features.bgp import BGPWindowFeatures


@dataclass
class WithdrawSpikeDetector(DetectorBase[BGPWindowFeatures]):
    name: ClassVar[str] = "withdraw_spike"
    min_silent_prefixes: int = 50

    def score(self, features: BGPWindowFeatures) -> list[Alert]:
        # "Silent" = a prefix that received withdrawals in the window and
        # has no covering announcement (no origin observed at all in the
        # same window). This excludes prefixes that flapped (W then A again).
        silent_prefixes = [
            p for p in features.withdraw_count_by_prefix if not features.origins_by_prefix.get(p)
        ]
        if len(silent_prefixes) < self.min_silent_prefixes:
            return []

        sample = sorted(silent_prefixes)[:5]
        return [
            Alert(
                timestamp_us=features.window_end_us,
                detector=self.name,
                severity="warning",
                entity=f"{len(silent_prefixes)} prefixes",
                summary=(
                    f"{len(silent_prefixes)} prefixes withdrawn without "
                    f"re-announcement (sample: {', '.join(sample)})"
                ),
                window_start_us=features.window_start_us,
                window_end_us=features.window_end_us,
                evidence={
                    "n_silent_prefixes": len(silent_prefixes),
                    "sample": sample,
                    "threshold": self.min_silent_prefixes,
                },
            )
        ]
