"""Route-leak detector based on valley-free path inference (RFC 7908 Type 1).

A standard *valley-free* AS-path has the shape ``(c2p)* (p2p)? (p2c)*``.
The classic Type-1 leak — a customer accepting a route from one provider
or peer and leaking it to another provider — produces a path that
violates this pattern (a "valley": a downhill p2c step followed by an
uphill c2p or p2p step).

This detector takes:

- A set of AS-relationship pairs (e.g. CAIDA's serial-2 inferred
  relationships, or operator-curated peering DB entries).
- A set of observed paths from a window of BGP records.

For each observed path it walks left-to-right, classifies each adjacent
ASN pair as ``c2p`` / ``p2p`` / ``p2c``, and flags any path that
contains a ``p2c`` step followed by a non-``p2c`` step. Unknown
relationships do not trigger an alert (no false positives from missing
data) but the unknown count is reported in evidence.

Operates over raw paths rather than the prefix-aggregated
``BGPWindowFeatures`` because path inspection is what the algorithm
needs.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from netpulse.alerts import Alert
from netpulse.storage.asrel_schema import ASREL_TABLE
from netpulse.storage.asrel_store import ASRelStore

Direction = Literal["c2p", "p2p", "p2c", "unknown"]

# Inverse of a relationship when traversed in the opposite direction.
_INVERSE = {"c2p": "p2c", "p2c": "c2p", "p2p": "p2p", "sibling": "sibling"}


@dataclass(slots=True)
class ObservedPath:
    """One BGP path observation flat enough for the route-leak detector."""

    prefix: str
    asns: list[int]
    peer_as: int
    timestamp_us: int


class ASRelationshipMap:
    """Lookup: ordered pair of ASNs -> direction the route goes when stepping a -> b."""

    pairs: dict[tuple[int, int], Direction]

    def __init__(self) -> None:
        self.pairs = {}

    @classmethod
    def from_store(cls, store: ASRelStore) -> ASRelationshipMap:
        rows = store.query(f"SELECT as_a, as_b, relationship FROM {ASREL_TABLE}")
        return cls.from_rows(rows)

    @classmethod
    def from_rows(cls, rows: Iterable[tuple[int, int, str]]) -> ASRelationshipMap:
        m = cls()
        for as_a, as_b, rel in rows:
            m.add(int(as_a), int(as_b), str(rel))
        return m

    def add(self, as_a: int, as_b: int, rel: str) -> None:
        if rel == "p2p":
            self.pairs[(as_a, as_b)] = "p2p"
            self.pairs[(as_b, as_a)] = "p2p"
        elif rel == "p2c":
            self.pairs[(as_a, as_b)] = "p2c"
            self.pairs[(as_b, as_a)] = "c2p"
        elif rel == "c2p":
            self.pairs[(as_a, as_b)] = "c2p"
            self.pairs[(as_b, as_a)] = "p2c"
        elif rel == "sibling":
            # Treat siblings as peer-equivalent for leak detection.
            self.pairs[(as_a, as_b)] = "p2p"
            self.pairs[(as_b, as_a)] = "p2p"

    def direction(self, a: int, b: int) -> Direction:
        return self.pairs.get((a, b), "unknown")


def is_valley(path: Sequence[int], rels: ASRelationshipMap) -> tuple[bool, list[Direction], int]:
    """Return ``(is_valley, per-step directions, unknown_count)``.

    A valley exists if any p2c step is followed by a c2p or p2p step at
    a later position in the path.
    """
    directions: list[Direction] = [
        rels.direction(path[i], path[i + 1]) for i in range(len(path) - 1)
    ]
    unknown = sum(1 for d in directions if d == "unknown")

    saw_p2c = False
    for d in directions:
        if d == "p2c":
            saw_p2c = True
        elif d in ("c2p", "p2p") and saw_p2c:
            return True, directions, unknown
    return False, directions, unknown


@dataclass
class RouteLeakDetector:
    """Flag observed BGP paths that are not valley-free."""

    name: ClassVar[str] = "route_leak"
    rels: ASRelationshipMap

    def score_paths(self, paths: Iterable[ObservedPath]) -> list[Alert]:
        alerts: list[Alert] = []
        for p in paths:
            valley, dirs, unknown = is_valley(p.asns, self.rels)
            if not valley:
                continue
            alerts.append(
                Alert(
                    timestamp_us=p.timestamp_us,
                    detector=self.name,
                    severity="warning",
                    entity=p.prefix,
                    summary=(
                        f"path {p.asns} for {p.prefix} is not valley-free (step directions: {dirs})"
                    ),
                    window_start_us=p.timestamp_us,
                    window_end_us=p.timestamp_us,
                    evidence={
                        "path": p.asns,
                        "step_directions": dirs,
                        "unknown_steps": unknown,
                        "peer_as": p.peer_as,
                    },
                )
            )
        return alerts


def parse_as_path(as_path: str | None) -> list[int] | None:
    """Parse a space-separated as-path string into a list of ints.

    Returns None if any segment is an AS-set or otherwise unparseable.
    """
    if not as_path:
        return None
    out: list[int] = []
    for token in as_path.split():
        if token.startswith("{"):
            return None
        try:
            out.append(int(token))
        except ValueError:
            return None
    return out
