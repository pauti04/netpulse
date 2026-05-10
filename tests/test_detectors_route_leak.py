from __future__ import annotations

from netpulse.detectors.route_leak import (
    ASRelationshipMap,
    ObservedPath,
    RouteLeakDetector,
    is_valley,
    parse_as_path,
)


def _rels(pairs: list[tuple[int, int, str]]) -> ASRelationshipMap:
    return ASRelationshipMap.from_rows([(a, b, r) for a, b, r in pairs])


def test_uphill_only_path_is_valley_free() -> None:
    # Customer -> provider -> tier-1: classic uphill.
    rels = _rels([(64500, 64600, "c2p"), (64600, 64700, "c2p")])
    valley, dirs, _ = is_valley([64500, 64600, 64700], rels)
    assert not valley
    assert dirs == ["c2p", "c2p"]


def test_uphill_then_peer_then_downhill_is_valley_free() -> None:
    # Standard valid path: customer -> provider -> peer -> customer.
    rels = _rels(
        [
            (64500, 64600, "c2p"),
            (64600, 64700, "p2p"),
            (64700, 64800, "p2c"),
        ]
    )
    valley, dirs, _ = is_valley([64500, 64600, 64700, 64800], rels)
    assert not valley
    assert dirs == ["c2p", "p2p", "p2c"]


def test_downhill_then_uphill_is_a_valley() -> None:
    # Provider hands route to customer, customer leaks back upstream:
    # the textbook RFC 7908 Type-1 leak.
    rels = _rels(
        [
            (64600, 64500, "p2c"),  # provider -> customer
            (64500, 64700, "c2p"),  # customer -> different provider
        ]
    )
    valley, dirs, _ = is_valley([64600, 64500, 64700], rels)
    assert valley
    assert dirs == ["p2c", "c2p"]


def test_unknown_relationships_do_not_create_a_valley() -> None:
    # Without relationship data we abstain (no false positives).
    rels = _rels([])  # empty
    valley, dirs, unknown = is_valley([1, 2, 3, 4, 5], rels)
    assert not valley
    assert dirs == ["unknown"] * 4
    assert unknown == 4


def test_detector_fires_on_mainone_pattern() -> None:
    # Approximation of the 2018 MainOne case: AS37282 (customer of AS4809)
    # appears as transit between AS4809 (provider) and AS15169 (Google),
    # which means the path went provider -> customer -> ... uphill again.
    rels = _rels(
        [
            (15562, 2914, "c2p"),
            (2914, 20485, "p2c"),  # NTT downhill to TransTelecom
            (20485, 4809, "c2p"),  # TransTelecom uphill to ChinaTelecom -> valley
            (4809, 37282, "p2c"),
            (37282, 15169, "c2p"),
        ]
    )
    detector = RouteLeakDetector(rels=rels)
    alerts = detector.score_paths(
        [
            ObservedPath(
                prefix="216.58.192.0/22",
                asns=[15562, 2914, 20485, 4809, 37282, 15169],
                peer_as=15562,
                timestamp_us=1_542_056_760_000_000,
            )
        ]
    )
    assert len(alerts) == 1
    a = alerts[0]
    assert a.detector == "route_leak"
    assert a.entity == "216.58.192.0/22"
    assert "valley-free" in a.summary
    assert a.evidence["path"] == [15562, 2914, 20485, 4809, 37282, 15169]
    assert "p2c" in a.evidence["step_directions"]


def test_parse_as_path_returns_ints() -> None:
    assert parse_as_path("3333 12859 17557") == [3333, 12859, 17557]


def test_parse_as_path_returns_none_for_as_set() -> None:
    assert parse_as_path("3333 {12859,12860} 17557") is None


def test_parse_as_path_returns_none_for_empty() -> None:
    assert parse_as_path(None) is None
    assert parse_as_path("") is None
