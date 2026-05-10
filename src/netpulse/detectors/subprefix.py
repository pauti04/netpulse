"""Sub-prefix hijack detector: flag more-specifics announced from an unauthorized AS."""

from __future__ import annotations

from typing import ClassVar

from netpulse.alerts import Alert
from netpulse.detectors.base import DetectorBase
from netpulse.detectors.baseline import BGPBaseline
from netpulse.features.bgp import BGPWindowFeatures


class SubPrefixHijackDetector(DetectorBase[BGPWindowFeatures]):
    name: ClassVar[str] = "subprefix_hijack"

    def __init__(self, baseline: BGPBaseline) -> None:
        self.baseline = baseline

    def score(self, features: BGPWindowFeatures) -> list[Alert]:
        alerts: list[Alert] = []
        for prefix, observed in features.origins_by_prefix.items():
            authorized = self.baseline.origins_for(prefix)
            if observed.issubset(authorized) and authorized:
                continue

            cover = self.baseline.most_specific_supernet(prefix)
            if cover is None:
                continue

            covering_prefix, legitimate = cover
            unauthorized = observed - legitimate - authorized
            if not unauthorized:
                continue

            observed_list = sorted(observed)
            unauth_list = sorted(unauthorized)
            legit_list = sorted(legitimate)
            alerts.append(
                Alert(
                    timestamp_us=features.window_end_us,
                    detector=self.name,
                    severity="critical",
                    entity=prefix,
                    summary=(
                        f"more-specific of {covering_prefix} "
                        f"(legit origins {legit_list}) "
                        f"announced from unauthorized origin(s) {unauth_list}"
                    ),
                    window_start_us=features.window_start_us,
                    window_end_us=features.window_end_us,
                    evidence={
                        "covering_prefix": covering_prefix,
                        "legitimate_origins": legit_list,
                        "observed_origins": observed_list,
                        "unauthorized_origins": unauth_list,
                    },
                )
            )
        return alerts
