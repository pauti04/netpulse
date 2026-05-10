"""Atlas reachability detector: flag global packet-loss spikes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from netpulse.alerts import Alert
from netpulse.detectors.base import DetectorBase
from netpulse.features.atlas import AtlasPingWindowFeatures


@dataclass
class AtlasLossSpikeDetector(DetectorBase[AtlasPingWindowFeatures]):
    """Flag windows where an unusually high share of probes saw full packet loss.

    Probe-individual flakiness is normal; correlated loss across many probes
    in a single short window is the reachability-degradation signal.
    """

    name: ClassVar[str] = "atlas_loss_spike"
    full_loss_rate_threshold: float = 0.20
    min_results: int = 100

    def score(self, features: AtlasPingWindowFeatures) -> list[Alert]:
        if features.n_results < self.min_results:
            return []
        if features.full_loss_rate < self.full_loss_rate_threshold:
            return []

        return [
            Alert(
                timestamp_us=features.window_end_us,
                detector=self.name,
                severity="critical",
                entity=f"msm:{features.msm_id}",
                summary=(
                    f"{features.n_full_loss}/{features.n_results} probes "
                    f"({features.full_loss_rate:.1%}) saw full packet loss "
                    f"in this window"
                ),
                window_start_us=features.window_start_us,
                window_end_us=features.window_end_us,
                evidence={
                    "msm_id": features.msm_id,
                    "n_results": features.n_results,
                    "n_full_loss": features.n_full_loss,
                    "n_partial_loss": features.n_partial_loss,
                    "full_loss_rate": features.full_loss_rate,
                    "any_loss_rate": features.any_loss_rate,
                    "threshold": self.full_loss_rate_threshold,
                },
            )
        ]
