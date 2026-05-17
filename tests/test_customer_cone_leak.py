from __future__ import annotations

from netpulse.detectors.customer_cone import CustomerConeMap
from netpulse.detectors.customer_cone_leak import (
    CustomerConeLeakDetector,
    classify_path,
)
from netpulse.detectors.route_leak import ASRelationshipMap, ObservedPath


def _rels(*pairs: tuple[int, int, str]) -> ASRelationshipMap:
    m = ASRelationshipMap()
    for a, b, rel in pairs:
        m.add(a, b, rel)
    return m


def test_cone_includes_transitive_p2c_descendants() -> None:
    rels = _rels((1, 2, "p2c"), (2, 3, "p2c"), (3, 4, "p2c"))
    cones = CustomerConeMap.from_relationships(rels)

    assert cones.cone(1) == frozenset({1, 2, 3, 4})
    assert cones.cone(2) == frozenset({2, 3, 4})
    assert cones.cone(4) == frozenset({4})  # leaf is its own cone


def test_cone_does_not_traverse_peering_or_provider_edges() -> None:
    rels = _rels((1, 2, "p2p"), (1, 3, "c2p"), (1, 4, "p2c"))
    cones = CustomerConeMap.from_relationships(rels)

    assert cones.cone(1) == frozenset({1, 4})
    assert 2 not in cones.cone(1)  # peer
    assert 3 not in cones.cone(1)  # provider


def test_classify_path_flags_downhill_then_uphill_as_valley() -> None:
    # Stub Google leak: provider Verizon 701 has Google 15169 as p2c customer;
    # Google's cone does NOT include NTT OCN 4713 (peer/lateral).
    rels = _rels((701, 15169, "p2c"))
    cones = CustomerConeMap.from_relationships(rels)

    # Step shapes for [701, 15169, 4713]:
    #   701 -> 15169: 15169 in cone(701) (direct customer) -> downhill
    #   15169 -> 4713: 4713 not in cone(15169) -> uphill
    leak, shapes = classify_path([701, 15169, 4713], cones)
    assert leak
    assert shapes == ["downhill", "uphill"]


def test_classify_path_does_not_flag_pure_uphill_climb() -> None:
    # 100 customer of 200, which is customer of 300. Path 100->200->300 is
    # the legit upward announce.
    rels = _rels((200, 100, "p2c"), (300, 200, "p2c"))
    cones = CustomerConeMap.from_relationships(rels)
    leak, shapes = classify_path([100, 200, 300], cones)
    assert not leak
    assert shapes == ["uphill", "uphill"]


def test_classify_path_does_not_flag_pure_downhill() -> None:
    rels = _rels((300, 200, "p2c"), (200, 100, "p2c"))
    cones = CustomerConeMap.from_relationships(rels)
    leak, shapes = classify_path([300, 200, 100], cones)
    assert not leak
    assert shapes == ["downhill", "downhill"]


def test_detector_emits_alert_with_path_evidence() -> None:
    rels = _rels((701, 15169, "p2c"))
    cones = CustomerConeMap.from_relationships(rels)
    det = CustomerConeLeakDetector(cones=cones)
    path = ObservedPath(
        prefix="203.0.113.0/24",
        asns=[701, 15169, 4713],
        peer_as=3333,
        timestamp_us=1_000_000_000,
    )
    alerts = det.score_paths([path])
    assert len(alerts) == 1
    a = alerts[0]
    assert a.detector == "customer_cone_leak"
    assert a.entity == "203.0.113.0/24"
    assert a.evidence["step_shapes"] == ["downhill", "uphill"]
    assert a.evidence["peer_as"] == 3333


def test_detector_silent_on_clean_path() -> None:
    rels = _rels((701, 15169, "p2c"), (15169, 99999, "p2c"))
    cones = CustomerConeMap.from_relationships(rels)
    det = CustomerConeLeakDetector(cones=cones)
    path = ObservedPath(
        prefix="203.0.113.0/24",
        asns=[701, 15169, 99999],  # pure downhill: provider -> customer -> sub-customer
        peer_as=3333,
        timestamp_us=1_000_000_000,
    )
    assert det.score_paths([path]) == []
