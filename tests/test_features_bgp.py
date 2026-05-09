from __future__ import annotations

from pathlib import Path

import pytest

from netpulse.features.bgp import extract_bgp_features
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord


def _rec(ts: int, prefix: str, origin: int | None, update_type: str = "A") -> BGPRecord:
    return BGPRecord(
        timestamp_us=ts,
        collector="rrc00",
        peer_as=64500,
        peer_ip="192.0.2.1",
        prefix=prefix,
        update_type=update_type,
        origin_as=origin,
        as_path=str(origin) if origin is not None else None,
    )


def test_extract_groups_by_prefix(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "bgp.duckdb") as store:
        store.write_batch(
            [
                _rec(1_000_000, "192.0.2.0/24", 64600),
                _rec(2_000_000, "192.0.2.0/24", 64600),
                _rec(3_000_000, "192.0.2.0/24", 64601),
                _rec(4_000_000, "203.0.113.0/24", 64602),
                _rec(5_000_000, "203.0.113.0/24", None, update_type="W"),
            ]
        )
        feats = extract_bgp_features(store, 0, 10_000_000)

    assert feats.origins_by_prefix["192.0.2.0/24"] == {64600, 64601}
    assert feats.origins_by_prefix["203.0.113.0/24"] == {64602}
    assert feats.announce_count_by_prefix["192.0.2.0/24"] == 3
    assert feats.announce_count_by_prefix["203.0.113.0/24"] == 1
    assert feats.withdraw_count_by_prefix["203.0.113.0/24"] == 1
    assert feats.announce_total == 4
    assert feats.withdraw_total == 1


def test_extract_filters_to_window(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "bgp.duckdb") as store:
        store.write_batch(
            [
                _rec(500_000, "192.0.2.0/24", 64600),  # before window
                _rec(1_500_000, "192.0.2.0/24", 64600),  # in window
                _rec(2_500_000, "192.0.2.0/24", 64600),  # at/after window end
            ]
        )
        feats = extract_bgp_features(store, 1_000_000, 2_000_000)

    assert feats.announce_count_by_prefix["192.0.2.0/24"] == 1


def test_extract_rejects_inverted_window(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "bgp.duckdb") as store, pytest.raises(ValueError):
        extract_bgp_features(store, 200, 100)


def test_extract_empty_store_returns_empty_features(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "bgp.duckdb") as store:
        feats = extract_bgp_features(store, 0, 10_000_000)
    assert feats.origins_by_prefix == {}
    assert feats.announce_total == 0
    assert feats.withdraw_total == 0
