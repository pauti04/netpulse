from __future__ import annotations

from pathlib import Path

from netpulse.detectors.rpki import RPKIInvalidDetector, RPKIValidator
from netpulse.features.bgp import BGPWindowFeatures
from netpulse.storage.rpki_schema import RPKIRecord
from netpulse.storage.rpki_store import RPKIStore


def _validator(rows: list[tuple[str, int, int]]) -> RPKIValidator:
    return RPKIValidator.from_rows(rows)


def test_validate_returns_valid_for_exact_match() -> None:
    v = _validator([("203.0.113.0/24", 64600, 24)])
    assert v.validate("203.0.113.0/24", 64600) == "valid"


def test_validate_returns_valid_for_more_specific_within_max_length() -> None:
    v = _validator([("203.0.112.0/22", 64600, 24)])
    assert v.validate("203.0.113.0/24", 64600) == "valid"


def test_validate_returns_invalid_when_origin_does_not_match() -> None:
    v = _validator([("203.0.112.0/22", 64600, 24)])
    assert v.validate("203.0.113.0/24", 64601) == "invalid"


def test_validate_returns_invalid_when_more_specific_than_max_length() -> None:
    # ROA only authorizes /22 itself; observed /24 is more-specific.
    v = _validator([("203.0.112.0/22", 64600, 22)])
    assert v.validate("203.0.113.0/24", 64600) == "invalid"


def test_validate_returns_not_found_when_no_covering_roa() -> None:
    v = _validator([("203.0.112.0/22", 64600, 24)])
    assert v.validate("198.51.100.0/24", 64600) == "not_found"


def test_validate_picks_one_matching_origin_when_multiple_roas_cover() -> None:
    # Two ROAs cover the prefix with different ASes; one matches the observation.
    v = _validator(
        [
            ("203.0.112.0/22", 64600, 24),
            ("203.0.112.0/22", 64601, 24),
        ]
    )
    assert v.validate("203.0.113.0/24", 64601) == "valid"


def test_detector_fires_only_on_invalid() -> None:
    v = _validator([("203.0.112.0/22", 64600, 24)])
    feats = BGPWindowFeatures(
        window_start_us=0,
        window_end_us=1_000_000,
        origins_by_prefix={
            "203.0.113.0/24": {64601},  # invalid
            "203.0.114.0/24": {64600},  # valid
            "198.51.100.0/24": {64602},  # not_found
        },
        announce_count_by_prefix={
            "203.0.113.0/24": 1,
            "203.0.114.0/24": 1,
            "198.51.100.0/24": 1,
        },
    )
    alerts = RPKIInvalidDetector(v).score(feats)
    flagged = sorted(a.entity for a in alerts)
    assert flagged == ["203.0.113.0/24"]
    assert alerts[0].evidence["invalid_origins"] == [64601]


def test_validator_loads_from_store(tmp_path: Path) -> None:
    p = tmp_path / "rpki.duckdb"
    with RPKIStore(p) as store:
        store.write_batch(
            [
                RPKIRecord(prefix="203.0.112.0/22", asn=64600, max_length=24),
                RPKIRecord(prefix="2001:db8::/32", asn=64602, max_length=48),
            ]
        )
        assert store.count() == 2
        v = RPKIValidator.from_store(store)

    assert v.validate("203.0.113.0/24", 64600) == "valid"
    assert v.validate("203.0.113.0/24", 64601) == "invalid"
    assert v.validate("2001:db8:cafe::/48", 64602) == "valid"
