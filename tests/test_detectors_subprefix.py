from __future__ import annotations

from pathlib import Path

from netpulse.detectors.baseline import BGPBaseline
from netpulse.detectors.subprefix import SubPrefixHijackDetector
from netpulse.features.bgp import BGPWindowFeatures
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord


def _features(origins: dict[str, set[int]]) -> BGPWindowFeatures:
    return BGPWindowFeatures(
        window_start_us=0,
        window_end_us=1_000_000,
        origins_by_prefix=origins,
        announce_count_by_prefix=dict.fromkeys(origins, 1),
    )


def test_flags_more_specific_from_unauthorized_origin() -> None:
    baseline = BGPBaseline.build({"203.0.112.0/21": {64600}})
    feats = _features({"203.0.113.0/24": {64601}})

    alerts = SubPrefixHijackDetector(baseline).score(feats)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.detector == "subprefix_hijack"
    assert a.entity == "203.0.113.0/24"
    assert a.severity == "critical"
    assert a.evidence["covering_prefix"] == "203.0.112.0/21"
    assert a.evidence["legitimate_origins"] == [64600]
    assert a.evidence["unauthorized_origins"] == [64601]


def test_ignores_more_specific_from_legitimate_origin() -> None:
    baseline = BGPBaseline.build({"203.0.112.0/21": {64600}})
    feats = _features({"203.0.113.0/24": {64600}})

    assert SubPrefixHijackDetector(baseline).score(feats) == []


def test_ignores_exact_match_with_authorized_origin() -> None:
    baseline = BGPBaseline.build({"192.0.2.0/24": {64600}})
    feats = _features({"192.0.2.0/24": {64600}})

    assert SubPrefixHijackDetector(baseline).score(feats) == []


def test_ignores_prefix_with_no_baseline_supernet() -> None:
    # No supernet in baseline -> we don't have evidence to call it a hijack.
    baseline = BGPBaseline.build({"192.0.2.0/24": {64600}})
    feats = _features({"203.0.113.0/24": {64601}})

    assert SubPrefixHijackDetector(baseline).score(feats) == []


def test_picks_most_specific_supernet() -> None:
    baseline = BGPBaseline.build(
        {
            "10.0.0.0/8": {64500},
            "10.1.0.0/16": {64600},  # more specific supernet — this is the legit owner
        }
    )
    feats = _features({"10.1.2.0/24": {64700}})

    alerts = SubPrefixHijackDetector(baseline).score(feats)

    assert len(alerts) == 1
    assert alerts[0].evidence["covering_prefix"] == "10.1.0.0/16"
    assert alerts[0].evidence["legitimate_origins"] == [64600]


def test_flags_exact_prefix_with_unauthorized_origin() -> None:
    # China-Telecom-2010-shaped: AS23724 announced AT&T's exact /23, no sub-
    # prefix involved. Baseline says AS7018 owns 12.5.58.0/23; observed AS23724
    # must fire alert.
    baseline = BGPBaseline.build({"12.5.58.0/23": {7018}})
    feats = _features({"12.5.58.0/23": {23724}})

    alerts = SubPrefixHijackDetector(baseline).score(feats)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.entity == "12.5.58.0/23"
    assert a.evidence["shape"] == "exact_prefix"
    assert a.evidence["legitimate_origins"] == [7018]
    assert a.evidence["unauthorized_origins"] == [23724]


def test_baseline_loads_from_duckdb_store(tmp_path: Path) -> None:
    with BGPStore(tmp_path / "rib.duckdb") as store:
        store.write_batch(
            [
                BGPRecord(
                    timestamp_us=0,
                    collector="rrc00",
                    peer_as=64500,
                    peer_ip="192.0.2.1",
                    prefix="203.0.112.0/21",
                    update_type="A",
                    origin_as=64600,
                    as_path="64600",
                ),
                BGPRecord(
                    timestamp_us=1,
                    collector="rrc00",
                    peer_as=64500,
                    peer_ip="192.0.2.1",
                    prefix="203.0.112.0/21",
                    update_type="A",
                    origin_as=64600,
                    as_path="64600",
                ),
            ]
        )
        baseline = BGPBaseline.from_store(store)

    assert baseline.origins_for("203.0.112.0/21") == {64600}
    assert baseline.most_specific_supernet("203.0.113.0/24") == ("203.0.112.0/21", {64600})
