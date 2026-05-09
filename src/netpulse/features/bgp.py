"""Per-window feature extraction for BGP records."""

from __future__ import annotations

from dataclasses import dataclass, field

from netpulse.storage.duckdb_store import BGPStore


@dataclass(slots=True)
class BGPWindowFeatures:
    """Aggregate features over a half-open ``[start_us, end_us)`` window."""

    window_start_us: int
    window_end_us: int
    origins_by_prefix: dict[str, set[int]] = field(default_factory=dict)
    announce_count_by_prefix: dict[str, int] = field(default_factory=dict)
    withdraw_count_by_prefix: dict[str, int] = field(default_factory=dict)

    @property
    def announce_total(self) -> int:
        return sum(self.announce_count_by_prefix.values())

    @property
    def withdraw_total(self) -> int:
        return sum(self.withdraw_count_by_prefix.values())


def extract_bgp_features(
    store: BGPStore,
    start_us: int,
    end_us: int,
) -> BGPWindowFeatures:
    """Aggregate per-prefix origins and announce/withdraw counts in a window."""
    if end_us <= start_us:
        raise ValueError("end_us must be greater than start_us")

    rows = store.query(
        """
        SELECT prefix, origin_as, update_type, COUNT(*) AS n
        FROM bgp_records
        WHERE timestamp_us >= ? AND timestamp_us < ?
        GROUP BY prefix, origin_as, update_type
        """,
        [start_us, end_us],
    )

    feats = BGPWindowFeatures(window_start_us=start_us, window_end_us=end_us)
    for prefix_raw, origin_raw, update_type_raw, n_raw in rows:
        prefix = str(prefix_raw)
        update_type = str(update_type_raw)
        n = int(n_raw)
        if update_type == "A":
            feats.announce_count_by_prefix[prefix] = (
                feats.announce_count_by_prefix.get(prefix, 0) + n
            )
            if origin_raw is not None:
                feats.origins_by_prefix.setdefault(prefix, set()).add(int(origin_raw))
        elif update_type == "W":
            feats.withdraw_count_by_prefix[prefix] = (
                feats.withdraw_count_by_prefix.get(prefix, 0) + n
            )

    return feats
