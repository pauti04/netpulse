from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from netpulse.storage.duckdb_store import BGPStore

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=262_144)
def _parse_network(prefix: str) -> tuple[_Network, str] | None:
    """Parse ``prefix`` into ``(network, canonical_str)`` once, then memoize.

    ``ipaddress.ip_network`` octet parsing dominated the sub-prefix
    detector's CPU (~190 ms over a 32K-prefix window) because every
    prefix was re-parsed twice per call — once for the exact-match
    lookup and once for the supernet walk — and again on every run.
    Caching collapses that to a single parse per distinct prefix string
    for the process lifetime. Bounded LRU so a long-lived streaming
    process can't grow it without limit.
    """
    try:
        net = ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return None
    return net, str(net)


@dataclass(slots=True)
class BGPBaseline:
    """Prefix -> set of legitimate origin ASNs, indexed by family + prefix length.

    Loaded from a DuckDB store populated with RIB entries (or any sustained
    set of announcements considered ground truth).
    """

    origins: dict[str, set[int]] = field(default_factory=dict)
    _v4: dict[int, list[ipaddress.IPv4Network]] = field(default_factory=dict)
    _v6: dict[int, list[ipaddress.IPv6Network]] = field(default_factory=dict)

    @classmethod
    def from_store(cls, store: BGPStore) -> BGPBaseline:
        rows = store.query(
            "SELECT prefix, origin_as FROM bgp_records "
            "WHERE update_type = 'A' AND origin_as IS NOT NULL "
            # Default routes appear in some RIB dumps but are useless as
            # supernets -- they "cover" every prefix and produce nonsense
            # sub-prefix-hijack alerts on legitimate announcements.
            "  AND prefix NOT IN ('0.0.0.0/0', '::/0')"
        )
        origins: dict[str, set[int]] = {}
        for prefix, origin_as in rows:
            origins.setdefault(str(prefix), set()).add(int(origin_as))
        return cls.build(origins)

    @classmethod
    def build(cls, origins: dict[str, set[int]]) -> BGPBaseline:
        # Canonicalize: dict key must match str(network) so lookups work even
        # when the input prefix has host bits set (e.g. "203.0.113.0/22").
        canonical: dict[str, set[int]] = {}
        v4: dict[int, list[ipaddress.IPv4Network]] = {}
        v6: dict[int, list[ipaddress.IPv6Network]] = {}
        for prefix, asns in origins.items():
            try:
                net = ipaddress.ip_network(prefix, strict=False)
            except ValueError:
                continue
            key = str(net)
            canonical.setdefault(key, set()).update(asns)
            if isinstance(net, ipaddress.IPv4Network):
                v4.setdefault(net.prefixlen, []).append(net)
            else:
                v6.setdefault(net.prefixlen, []).append(net)
        return cls(origins=canonical, _v4=v4, _v6=v6)

    def origins_for(self, prefix: str) -> set[int]:
        parsed = _parse_network(prefix)
        if parsed is None:
            return set()
        return self.origins.get(parsed[1], set())

    def covering_supernets(self, prefix: str) -> Iterable[tuple[str, set[int]]]:
        """Yield (supernet, origins) pairs for every baseline supernet of ``prefix``.

        Excludes the prefix itself. Yielded longest-prefix-first so the caller
        can stop at the most-specific match.
        """
        parsed = _parse_network(prefix)
        if parsed is None:
            return
        target = parsed[0]

        if isinstance(target, ipaddress.IPv4Network):
            for plen in sorted(self._v4, reverse=True):
                if plen >= target.prefixlen:
                    continue
                for v4 in self._v4[plen]:
                    if v4.supernet_of(target):
                        yield str(v4), self.origins[str(v4)]
        else:
            for plen in sorted(self._v6, reverse=True):
                if plen >= target.prefixlen:
                    continue
                for v6 in self._v6[plen]:
                    if v6.supernet_of(target):
                        yield str(v6), self.origins[str(v6)]

    def most_specific_supernet(self, prefix: str) -> tuple[str, set[int]] | None:
        for match in self.covering_supernets(prefix):
            return match
        return None
