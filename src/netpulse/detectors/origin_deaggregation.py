"""Origin-deaggregation detector.

Fires when a single origin AS suddenly emits a large burst of
more-specific (/23-or-longer) prefixes in the observation window.
The most-famous example is Telekom Malaysia 2015-06-12 (AS4788),
which re-announced ~179k of its own /16s as /23 sub-prefixes through
its upstream AS3549 (Level 3) -- causing global RIB churn even
though every announce had a legitimate origin so neither
``MOASDetector`` nor ``SubPrefixHijackDetector`` fires.

Detection is shape-only -- it does not need a baseline:

* The origin's distinct prefix count in the window must exceed
  ``min_distinct_prefixes`` (default 200).
* The fraction of those prefixes that are /23 or more-specific
  must exceed ``min_long_prefix_share`` (default 0.7).

Both thresholds together rule out normal multi-prefix operators
(an ISP announcing its 80 /16s isn't deaggregation) while catching
the Telekom-Malaysia shape (thousands of /23 announces in minutes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from netpulse.alerts import Alert
from netpulse.features.bgp import BGPWindowFeatures

_LONG_PREFIX_LEN: Final[int] = 23
"""Prefix length at which we start treating an announce as a "more-specific"."""


@dataclass(slots=True)
class OriginDeaggregationDetector:
    """Per-origin burst-of-more-specifics detector.

    :param min_distinct_prefixes: minimum prefix count from a single
        origin in the window before the detector considers firing.
    :param min_long_prefix_share: minimum share of those prefixes that
        must be /23 or more-specific.
    """

    name: str = "origin_deaggregation"
    min_distinct_prefixes: int = 200
    min_long_prefix_share: float = 0.7

    def score(self, features: BGPWindowFeatures) -> list[Alert]:
        # Invert origins_by_prefix: count per origin AS, plus how many
        # of those prefixes are long (/23+).
        prefixes_by_origin: dict[int, list[str]] = {}
        for prefix, origins in features.origins_by_prefix.items():
            for origin in origins:
                prefixes_by_origin.setdefault(origin, []).append(prefix)

        alerts: list[Alert] = []
        for origin, prefixes in prefixes_by_origin.items():
            total = len(prefixes)
            if total < self.min_distinct_prefixes:
                continue
            long_count = sum(1 for p in prefixes if _prefix_len(p) >= _LONG_PREFIX_LEN)
            share = long_count / total
            if share < self.min_long_prefix_share:
                continue
            alerts.append(
                Alert(
                    detector=self.name,
                    severity="warning",
                    entity=f"AS{origin}",
                    summary=(
                        f"AS{origin} announced {total} distinct prefixes in the "
                        f"window with {long_count} ({share * 100:.0f}%) at /{_LONG_PREFIX_LEN}+ "
                        "— deaggregation or mass leak shape"
                    ),
                    timestamp_us=features.window_end_us,
                    window_start_us=features.window_start_us,
                    window_end_us=features.window_end_us,
                    evidence={
                        "origin_as": origin,
                        "distinct_prefixes": total,
                        "long_prefix_count": long_count,
                        "long_prefix_share": round(share, 4),
                        "min_distinct_prefixes": self.min_distinct_prefixes,
                        "min_long_prefix_share": self.min_long_prefix_share,
                    },
                )
            )
        return alerts


def _prefix_len(prefix: str) -> int:
    """Return the bit-length of ``prefix`` (the ``/N`` suffix).

    Returns 0 for malformed input -- malformed prefixes don't count as
    long so they're never treated as deaggregation evidence.
    """
    if "/" not in prefix:
        return 0
    try:
        return int(prefix.rsplit("/", 1)[1])
    except ValueError:
        return 0
