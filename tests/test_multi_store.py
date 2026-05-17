from __future__ import annotations

from pathlib import Path

import pytest

from netpulse.detectors.baseline import BGPBaseline
from netpulse.features.bgp import extract_bgp_features
from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.multi_store import MultiStoreBGPView
from netpulse.storage.schema import BGPRecord


def _rec(prefix: str, origin_as: int, ts_us: int) -> BGPRecord:
    return BGPRecord(
        timestamp_us=ts_us,
        collector="test",
        peer_as=64500,
        peer_ip="192.0.2.1",
        prefix=prefix,
        update_type="A",
        origin_as=origin_as,
        as_path=str(origin_as),
    )


@pytest.fixture
def two_collectors(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "rrc00.duckdb"
    b = tmp_path / "rrc14.duckdb"
    with BGPStore(a) as sa:
        sa.write_batch([_rec("203.0.113.0/24", 64601, 1_000_000)])
    with BGPStore(b) as sb:
        sb.write_batch(
            [
                _rec("203.0.113.0/24", 64601, 2_000_000),  # same hijack, other collector
                _rec("198.51.100.0/24", 64700, 3_000_000),  # collector-B-only evidence
            ]
        )
    return a, b


def test_multi_store_unions_counts_across_attached_databases(
    two_collectors: tuple[Path, Path],
) -> None:
    a, b = two_collectors
    with MultiStoreBGPView([a, b]) as view:
        assert view.count() == 3
        by_src = {Path(p).name: n for _, p, n in view.count_by_source()}
        assert by_src == {"rrc00.duckdb": 1, "rrc14.duckdb": 2}


def test_features_over_multi_store_see_union_evidence(
    two_collectors: tuple[Path, Path],
) -> None:
    a, b = two_collectors
    with MultiStoreBGPView([a, b]) as view:
        feats = extract_bgp_features(view, 0, 10_000_000)  # type: ignore[arg-type]

    assert feats.announce_count_by_prefix["203.0.113.0/24"] == 2
    assert feats.announce_count_by_prefix["198.51.100.0/24"] == 1
    assert feats.origins_by_prefix["203.0.113.0/24"] == {64601}
    assert feats.origins_by_prefix["198.51.100.0/24"] == {64700}


def test_multi_store_with_subprefix_detector_sees_collector_b_only_evidence(
    tmp_path: Path,
) -> None:
    """rrc00 sees only the legit announce; rrc14 sees the hijack. Detector
    fires only when both stores are unioned in."""
    a = tmp_path / "a.duckdb"
    b = tmp_path / "b.duckdb"
    with BGPStore(a) as sa:
        sa.write_batch([_rec("203.0.112.0/22", 64600, 1_000_000)])
    with BGPStore(b) as sb:
        sb.write_batch([_rec("203.0.113.0/24", 64999, 2_000_000)])  # hijack visible at B only

    baseline = BGPBaseline.build({"203.0.112.0/22": {64600}})

    # rrc00 alone: no sub-prefix hijack visible.
    with BGPStore(a) as sa:
        feats_a = extract_bgp_features(sa, 0, 10_000_000)
    assert "203.0.113.0/24" not in feats_a.origins_by_prefix

    # Union view: hijack now visible.
    with MultiStoreBGPView([a, b]) as view:
        feats_u = extract_bgp_features(view, 0, 10_000_000)  # type: ignore[arg-type]
    assert feats_u.origins_by_prefix["203.0.113.0/24"] == {64999}

    from netpulse.detectors.subprefix import SubPrefixHijackDetector

    det = SubPrefixHijackDetector(baseline)
    assert det.score(feats_a) == []
    alerts = det.score(feats_u)
    assert len(alerts) == 1
    assert alerts[0].entity == "203.0.113.0/24"


def test_multi_store_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        MultiStoreBGPView([tmp_path / "does_not_exist.duckdb"])


def test_multi_store_empty_paths_raises() -> None:
    with pytest.raises(ValueError):
        MultiStoreBGPView([])
