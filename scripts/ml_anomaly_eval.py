"""Evaluate the unsupervised BGP anomaly scorer; write docs/ml_eval.json.

Loads the committed feature table, runs an Isolation Forest per incident
(unsupervised — labels withheld), and reports average precision + lift
over the base rate. Also reports the in-window sub-prefix-conflict rule
as a baseline.

    uv run --extra ml python scripts/ml_anomaly_eval.py
"""

from __future__ import annotations

import json
from pathlib import Path

from netpulse.ml.anomaly import (
    FEATURE_NAMES,
    RankingEval,
    evaluate_ranking,
    score_isolation_forest,
)

REPO = Path(__file__).resolve().parent.parent


def main() -> None:
    import pyarrow.parquet as pq

    table = pq.read_table(REPO / "data" / "ml" / "hijack_features.parquet")
    df = table.to_pydict()
    incidents = sorted(set(df["incident"]))

    results: dict[str, object] = {}
    rows_out = []
    for inc in incidents:
        idx = [i for i, x in enumerate(df["incident"]) if x == inc]
        matrix = [[float(df[f][i]) for f in FEATURE_NAMES] for i in idx]
        labels = [int(df["is_culprit"][i]) for i in idx]

        scores = score_isolation_forest(matrix)
        ev: RankingEval = evaluate_ranking(scores, labels)

        # Rule baseline: rank by the sub_conflict feature alone.
        conflict_idx = FEATURE_NAMES.index("sub_conflict")
        rule_scores = [matrix[i][conflict_idx] for i in range(len(matrix))]
        rule_ev = evaluate_ranking(rule_scores, labels)

        rows_out.append(
            (
                inc,
                ev.n,
                ev.n_positive,
                ev.base_rate,
                ev.average_precision,
                ev.lift,
                rule_ev.average_precision,
            )
        )
        results[inc] = {
            "n": ev.n,
            "n_positive": ev.n_positive,
            "base_rate": round(ev.base_rate, 4),
            "isolation_forest_ap": round(ev.average_precision, 4),
            "isolation_forest_lift": round(ev.lift, 2),
            "rule_conflict_ap": round(rule_ev.average_precision, 4),
        }

    out = REPO / "docs" / "ml_eval.json"
    out.write_text(json.dumps({"results": results, "features": list(FEATURE_NAMES)}, indent=2))

    print(f"{'incident':<18}{'obs':>7}{'pos':>6}{'base%':>7}{'IF-AP':>8}{'lift':>7}{'rule-AP':>9}")
    for inc, n, p, base, ap, lift, rap in rows_out:
        print(f"{inc:<18}{n:>7}{p:>6}{100 * base:>6.1f}%{ap:>8.3f}{lift:>6.1f}x{rap:>9.3f}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
