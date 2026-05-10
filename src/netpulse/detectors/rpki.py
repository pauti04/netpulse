"""RPKI Origin Validation detector.

Implements the standard three-way classification from RFC 6483 / 6811:

- **Valid** — at least one ROA covers (prefix, asn) with prefix length within
  ``max_length``.
- **Invalid** — at least one ROA covers the prefix at the right length, but
  none of the matching ROAs authorize the observed origin AS.
- **NotFound** — no covering ROA at any length.

The detector emits an Alert only on **Invalid** observations.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar, Literal

from netpulse.alerts import Alert
from netpulse.detectors.base import DetectorBase
from netpulse.features.bgp import BGPWindowFeatures
from netpulse.storage.rpki_schema import RPKI_VRPS_TABLE
from netpulse.storage.rpki_store import RPKIStore

ValidationOutcome = Literal["valid", "invalid", "not_found"]


@dataclass(slots=True)
class _ROA:
    asn: int
    max_length: int


class RPKIValidator:
    """Lookup structure: prefix (str) -> list of authorized (asn, max_length)."""

    by_prefix_v4: dict[ipaddress.IPv4Network, list[_ROA]]
    by_prefix_v6: dict[ipaddress.IPv6Network, list[_ROA]]

    def __init__(self) -> None:
        self.by_prefix_v4 = {}
        self.by_prefix_v6 = {}

    @classmethod
    def from_store(cls, store: RPKIStore) -> RPKIValidator:
        rows = store.query(f"SELECT prefix, asn, max_length FROM {RPKI_VRPS_TABLE}")
        return cls.from_rows(rows)

    @classmethod
    def from_rows(cls, rows: Iterable[tuple[str, int, int]]) -> RPKIValidator:
        v = cls()
        for prefix, asn, max_length in rows:
            try:
                net = ipaddress.ip_network(str(prefix), strict=False)
            except ValueError:
                continue
            roa = _ROA(asn=int(asn), max_length=int(max_length))
            if isinstance(net, ipaddress.IPv4Network):
                v.by_prefix_v4.setdefault(net, []).append(roa)
            else:
                v.by_prefix_v6.setdefault(net, []).append(roa)
        return v

    def validate(self, prefix: str, asn: int) -> ValidationOutcome:
        """RFC 6811 origin validation.

        - "Valid": some VRP covers the prefix AND has the right ASN AND the
          observed length is within ``max_length``.
        - "Invalid": some VRP covers the prefix, but none Match the route.
        - "NotFound": no VRP covers the prefix at any length.
        """
        try:
            target = ipaddress.ip_network(prefix, strict=False)
        except ValueError:
            return "not_found"

        any_covering = False

        if isinstance(target, ipaddress.IPv4Network):
            for v4_net, roas4 in self.by_prefix_v4.items():
                if v4_net.prefixlen > target.prefixlen:
                    continue
                if not v4_net.supernet_of(target):
                    continue
                any_covering = True
                for r in roas4:
                    if r.asn != asn:
                        continue
                    if v4_net.prefixlen <= target.prefixlen <= r.max_length:
                        return "valid"
        else:
            for v6_net, roas6 in self.by_prefix_v6.items():
                if v6_net.prefixlen > target.prefixlen:
                    continue
                if not v6_net.supernet_of(target):
                    continue
                any_covering = True
                for r in roas6:
                    if r.asn != asn:
                        continue
                    if v6_net.prefixlen <= target.prefixlen <= r.max_length:
                        return "valid"

        return "invalid" if any_covering else "not_found"


class RPKIInvalidDetector(DetectorBase[BGPWindowFeatures]):
    """Flag observations whose (prefix, origin_asn) is RPKI-invalid."""

    name: ClassVar[str] = "rpki_invalid"

    def __init__(self, validator: RPKIValidator) -> None:
        self.validator = validator

    def score(self, features: BGPWindowFeatures) -> list[Alert]:
        alerts: list[Alert] = []
        for prefix, origins in features.origins_by_prefix.items():
            invalid_origins = sorted(
                asn for asn in origins if self.validator.validate(prefix, asn) == "invalid"
            )
            if not invalid_origins:
                continue
            alerts.append(
                Alert(
                    timestamp_us=features.window_end_us,
                    detector=self.name,
                    severity="critical",
                    entity=prefix,
                    summary=(f"{prefix} announced from RPKI-invalid origin(s) {invalid_origins}"),
                    window_start_us=features.window_start_us,
                    window_end_us=features.window_end_us,
                    evidence={
                        "invalid_origins": invalid_origins,
                        "all_observed_origins": sorted(origins),
                    },
                )
            )
        return alerts
