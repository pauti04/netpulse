from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass, field

from netpulse.storage.duckdb_store import BGPStore


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
        try:
            key = str(ipaddress.ip_network(prefix, strict=False))
        except ValueError:
            return set()
        return self.origins.get(key, set())

    def covering_supernets(self, prefix: str) -> Iterable[tuple[str, set[int]]]:
        """Yield (supernet, origins) pairs for every baseline supernet of ``prefix``.

        Excludes the prefix itself. Yielded longest-prefix-first so the caller
        can stop at the most-specific match.
        """
        try:
            target = ipaddress.ip_network(prefix, strict=False)
        except ValueError:
            return

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
