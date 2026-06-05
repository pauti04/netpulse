"""Tests for forensic propagation reconstruction.

`build_timeline` is pure and covers the derived-property + curve math.
`reconstruct_propagation` is exercised against a real in-memory BGPStore
in both origin (hijack) and transit (leak) modes.
"""

from __future__ import annotations

from pathlib import Path

from netpulse.forensics import (
    build_timeline,
    reconstruct_propagation,
)
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord

# ----- pure assembler -----


def test_build_timeline_sorts_and_offsets() -> None:
    tl = build_timeline(
        subject_asn=17557,
        prefix="208.65.153.0/24",
        mode="origin",
        onset_us=1_000_000,
        window_start_us=0,
        window_end_us=10_000_000,
        total_peers_in_window=10,
        peer_first_seen_us={3333: 1_000_000, 7018: 3_000_000, 6461: 2_000_000},
        distinct_paths=5,
    )
    # Sorted ascending by first_seen.
    assert [p.peer_as for p in tl.peers_reached] == [3333, 6461, 7018]
    assert tl.reached_count == 3
    assert tl.spread_pct == 30.0
    assert tl.time_to_first_us == 0  # 1_000_000 - 1_000_000
    assert tl.time_to_full_us == 2_000_000  # 3_000_000 - 1_000_000
    assert tl.distinct_paths == 5


def test_spread_pct_zero_when_no_peers() -> None:
    tl = build_timeline(
        subject_asn=1,
        prefix=None,
        mode="transit",
        onset_us=0,
        window_start_us=0,
        window_end_us=1,
        total_peers_in_window=0,
        peer_first_seen_us={},
        distinct_paths=0,
    )
    assert tl.spread_pct == 0.0
    assert tl.time_to_first_us is None
    assert tl.time_to_full_us is None
    assert tl.spread_curve() == []


def test_spread_curve_is_cumulative_and_monotonic() -> None:
    tl = build_timeline(
        subject_asn=1,
        prefix=None,
        mode="transit",
        onset_us=0,
        window_start_us=0,
        window_end_us=100,
        total_peers_in_window=4,
        peer_first_seen_us={10: 0, 20: 25, 30: 50, 40: 100},
        distinct_paths=1,
    )
    curve = tl.spread_curve(n_buckets=4)
    counts = [c for _, c in curve]
    assert counts == sorted(counts)  # monotonic non-decreasing
    assert counts[-1] == 4  # everyone reached by the last bucket
    assert all(0 <= c <= 4 for c in counts)


def test_spread_curve_instantaneous() -> None:
    tl = build_timeline(
        subject_asn=1,
        prefix=None,
        mode="transit",
        onset_us=0,
        window_start_us=0,
        window_end_us=10,
        total_peers_in_window=3,
        peer_first_seen_us={10: 5, 20: 5, 30: 5},
        distinct_paths=1,
    )
    # All first-seen at the same instant -> single bucket holding everyone.
    assert tl.spread_curve() == [(5, 3)]


def test_negative_offset_clamped() -> None:
    # A peer that saw the prefix *before* the recorded onset (onset is a
    # detection artifact, not ground truth) should clamp to 0, not go negative.
    tl = build_timeline(
        subject_asn=1,
        prefix=None,
        mode="origin",
        onset_us=5_000_000,
        window_start_us=0,
        window_end_us=10_000_000,
        total_peers_in_window=2,
        peer_first_seen_us={10: 4_000_000, 20: 6_000_000},
        distinct_paths=1,
    )
    assert tl.time_to_first_us == 0
    curve = tl.spread_curve(n_buckets=2)
    assert all(off >= 0 for off, _ in curve)


# ----- store-driven reconstruction -----


def _rec(ts: int, peer: int, prefix: str, origin: int, path: str) -> BGPRecord:
    return BGPRecord(
        timestamp_us=ts,
        collector="rrc00",
        peer_as=peer,
        peer_ip="192.0.2.1",
        prefix=prefix,
        update_type="A",
        origin_as=origin,
        as_path=path,
    )


def test_reconstruct_origin_mode(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "b.duckdb") as store:
        store.write_batch(
            [
                # The hijack: AS999 origins 10.0.0.0/24, seen by 3 peers.
                _rec(1_000_000, 100, "10.0.0.0/24", 999, "100 999"),
                _rec(2_000_000, 200, "10.0.0.0/24", 999, "200 42 999"),
                _rec(3_000_000, 300, "10.0.0.0/24", 999, "300 999"),
                # Background: a different, legitimate prefix from a 4th peer.
                _rec(1_500_000, 400, "10.9.9.0/24", 555, "400 555"),
            ]
        )
        tl = reconstruct_propagation(
            store,
            subject_asn=999,
            prefix="10.0.0.0/24",
            onset_us=1_000_000,
            window_start_us=0,
            window_end_us=10_000_000,
        )
    assert tl.mode == "origin"
    assert tl.total_peers_in_window == 4  # 100,200,300,400 all announced something
    assert tl.reached_count == 3  # only 100,200,300 saw the hijack
    assert tl.spread_pct == 75.0
    assert tl.distinct_paths == 3
    assert tl.time_to_full_us == 2_000_000


def test_reconstruct_transit_mode_matches_interior_hop(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "b.duckdb") as store:
        store.write_batch(
            [
                # AS777 leaks as an interior hop on 2 peers' paths.
                _rec(1_000_000, 100, "10.0.0.0/24", 42, "100 777 42"),
                _rec(2_000_000, 200, "10.1.0.0/24", 42, "200 777 42"),
                # A path where 777 is the *origin*, not interior -> still
                # matches "transit" contains, which is fine: it traversed 777.
                # A path that doesn't include 777 at all -> excluded.
                _rec(1_500_000, 300, "10.2.0.0/24", 42, "300 99 42"),
            ]
        )
        tl = reconstruct_propagation(
            store,
            subject_asn=777,
            prefix=None,
            onset_us=1_000_000,
            window_start_us=0,
            window_end_us=10_000_000,
        )
    assert tl.mode == "transit"
    assert tl.reached_count == 2  # peers 100, 200; not 300
    assert {p.peer_as for p in tl.peers_reached} == {100, 200}


def test_reconstruct_empty_when_no_match(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "b.duckdb") as store:
        store.write_batch([_rec(1_000_000, 100, "10.0.0.0/24", 42, "100 42")])
        tl = reconstruct_propagation(
            store,
            subject_asn=999,
            prefix="10.0.0.0/24",
            onset_us=1_000_000,
            window_start_us=0,
            window_end_us=10_000_000,
        )
    assert tl.reached_count == 0
    assert tl.spread_pct == 0.0
