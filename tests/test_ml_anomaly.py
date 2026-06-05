"""Tests for the ML anomaly layer.

`extract_features` and the ranking-eval math are pure and tested here.
The scikit-learn scorer is smoke-tested behind the optional `[ml]` extra
(skipped if sklearn isn't installed).
"""

from __future__ import annotations

import pytest

from netpulse.ml.anomaly import (
    FEATURE_NAMES,
    ObservationRow,
    RankingEval,
    evaluate_ranking,
    extract_features,
)


def _row(
    prefix: str,
    origin: int,
    peers: int = 1,
    paths: int = 1,
    mean_pl: float = 3.0,
    min_pl: float = 3.0,
) -> ObservationRow:
    return ObservationRow(
        prefix=prefix,
        origin_as=origin,
        n_peers=peers,
        n_paths=paths,
        mean_path_len=mean_pl,
        min_path_len=min_pl,
    )


# ----- feature extraction -----


def test_feature_matrix_shape_and_keys() -> None:
    rows = [_row("10.0.0.0/24", 100), _row("10.1.0.0/22", 200)]
    matrix, keys = extract_features(rows)
    assert len(matrix) == 2
    assert all(len(r) == len(FEATURE_NAMES) for r in matrix)
    assert keys == ["10.0.0.0/24@AS100", "10.1.0.0/22@AS200"]


def test_is_24_and_prefix_len_features() -> None:
    matrix, _ = extract_features([_row("10.0.0.0/24", 100), _row("10.0.0.0/22", 100)])
    pl = FEATURE_NAMES.index("prefix_len")
    is24 = FEATURE_NAMES.index("is_24")
    assert matrix[0][pl] == 24.0 and matrix[0][is24] == 1.0
    assert matrix[1][pl] == 22.0 and matrix[1][is24] == 0.0


def test_moas_degree_counts_distinct_origins_per_prefix() -> None:
    rows = [_row("10.0.0.0/24", 100), _row("10.0.0.0/24", 200), _row("10.9.0.0/24", 100)]
    matrix, _ = extract_features(rows)
    md = FEATURE_NAMES.index("moas_degree")
    assert matrix[0][md] == 2.0  # 10.0.0.0/24 has two origins
    assert matrix[2][md] == 1.0  # 10.9.0.0/24 has one


def test_sub_conflict_detects_more_specific_of_another_origin() -> None:
    # 10.0.0.0/24 is a more-specific of 10.0.0.0/22 announced by a *different* origin.
    rows = [_row("10.0.0.0/22", 200), _row("10.0.0.0/24", 999)]
    matrix, _ = extract_features(rows)
    sc = FEATURE_NAMES.index("sub_conflict")
    assert matrix[1][sc] == 1.0  # the /24 conflicts with the /22 from AS200
    assert matrix[0][sc] == 0.0  # the /22 has no shorter covering prefix


def test_sub_conflict_ignores_same_origin_more_specific() -> None:
    # Same origin deaggregating its own space is NOT a conflict.
    rows = [_row("10.0.0.0/22", 100), _row("10.0.0.0/24", 100)]
    matrix, _ = extract_features(rows)
    sc = FEATURE_NAMES.index("sub_conflict")
    assert matrix[1][sc] == 0.0


def test_malformed_prefix_never_dropped() -> None:
    matrix, keys = extract_features([_row("not-a-prefix", 1), _row("10.0.0.0/24", 2)])
    assert len(matrix) == 2 and len(keys) == 2


# ----- ranking evaluation -----


def test_evaluate_ranking_perfect_separation() -> None:
    pytest.importorskip("sklearn")  # evaluate_ranking uses average_precision_score
    # scores rank all positives above all negatives -> AP = 1.0
    scores = [0.9, 0.8, 0.1, 0.05]
    labels = [1, 1, 0, 0]
    ev = evaluate_ranking(scores, labels)
    assert ev.n == 4
    assert ev.n_positive == 2
    assert ev.base_rate == 0.5
    assert ev.average_precision == pytest.approx(1.0)
    assert ev.lift == pytest.approx(2.0)  # AP / base_rate


def test_evaluate_ranking_all_one_class_is_zero() -> None:
    pytest.importorskip("sklearn")
    ev = evaluate_ranking([0.5, 0.5], [0, 0])
    assert ev.average_precision == 0.0
    assert ev.lift == 0.0


def test_ranking_lift_zero_when_no_positives() -> None:
    ev = RankingEval(n=10, n_positive=0, base_rate=0.0, average_precision=0.0)
    assert ev.lift == 0.0
