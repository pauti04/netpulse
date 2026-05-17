"""Customer-cone derivation from CAIDA-style AS-relationship data.

A given AS's *customer cone* is the set of ASes reachable from it by
following ``p2c`` edges only — transitively, the ASes it can announce
upstream as legitimate customer routes. Customer cones are the cleaner
input to leak detection than raw bilateral relationships, because they
capture the legitimacy of *transit* announcements rather than just
adjacent-pair direction inference.

This module derives cones lazily from an :class:`ASRelationshipMap`
(which is itself loaded from CAIDA's serial-2 inferred relationships
via :class:`netpulse.storage.asrel_store.ASRelStore`). Lazy because the
all-pairs cone computation is O(N · |V|) in the worst case but typical
detection runs only need cones for a few hundred distinct ASes.

The detector that consumes this lives in
:mod:`netpulse.detectors.customer_cone_leak`. See
``docs/paper.md`` §7 for why we prefer cones over raw valley-free when
checking observed transit paths.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from netpulse.detectors.route_leak import ASRelationshipMap


@dataclass(slots=True)
class CustomerConeMap:
    """Lazy-cache of customer cones derived from an AS-relationship map."""

    _p2c: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    _cache: dict[int, frozenset[int]] = field(default_factory=dict)

    @classmethod
    def from_relationships(cls, rels: ASRelationshipMap) -> CustomerConeMap:
        m = cls()
        for (a, b), direction in rels.pairs.items():
            if direction == "p2c":
                m._p2c[a].add(b)
        return m

    def cone(self, asn: int) -> frozenset[int]:
        """Return the transitive customer cone of ``asn`` (inclusive of ``asn`` itself)."""
        cached = self._cache.get(asn)
        if cached is not None:
            return cached
        seen: set[int] = {asn}
        q: deque[int] = deque([asn])
        while q:
            cur = q.popleft()
            for child in self._p2c.get(cur, ()):
                if child not in seen:
                    seen.add(child)
                    q.append(child)
        result = frozenset(seen)
        self._cache[asn] = result
        return result

    def contains(self, parent_asn: int, candidate_asn: int) -> bool:
        """True iff ``candidate_asn`` is in the transitive customer cone of ``parent_asn``."""
        return candidate_asn in self.cone(parent_asn)

    def precompute(self, asns: Iterable[int]) -> None:
        """Eagerly populate the cache for a known set of ASNs."""
        for a in asns:
            self.cone(a)
