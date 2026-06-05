"""Unsupervised anomaly detection over per-prefix BGP observations.

Motivation. The rule-based detectors require a *baseline* (a RIB snapshot
of legitimate origins) to flag a hijack. An interesting question for an
operator without that baseline: can the hijacked announcements be
surfaced from **observable features alone**, with no labels and no
ground-truth origins?

This module answers it with an Isolation Forest over scale-invariant
per-observation features, evaluated as a *ranking* problem (does the
model score the known-anomalous announcements above the benign ones?).
We report average precision and lift over the base rate — the correct
metrics for a rare-event ranking task — rather than accuracy, which is
meaningless at a 3–11% positive rate.

Design notes:
- Features are deliberately **scale-invariant** (no raw "how many
  prefixes did this origin announce" count). Including origin volume
  leaks the label on these incidents — the culprit AS is trivially the
  biggest announcer — and inflates supervised scores to a meaningless
  1.0. Leaving it out is the honest choice and is documented in
  `docs/ml/README.md`.
- `extract_features` is pure (operates on plain row tuples), so the
  feature engineering is unit-tested without scikit-learn or DuckDB.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

FEATURE_NAMES: tuple[str, ...] = (
    "prefix_len",  # /N mask length
    "is_24",  # 1 if exactly /24 (the common hijack granularity)
    "moas_degree",  # distinct origins announcing this exact prefix in-window
    "sub_conflict",  # 1 if a less-specific of this prefix is announced by another origin
    "n_peers",  # distinct vantage points that observed (prefix, origin)
    "n_paths",  # distinct AS paths carrying it
    "mean_path_len",  # mean AS-path length
    "min_path_len",  # min AS-path length (short paths = closer/odder origin)
)


@dataclass(slots=True)
class ObservationRow:
    """One aggregated (prefix, origin) observation from a BGP window."""

    prefix: str
    origin_as: int
    n_peers: int
    n_paths: int
    mean_path_len: float
    min_path_len: float


def extract_features(
    rows: list[ObservationRow],
) -> tuple[list[list[float]], list[str]]:
    """Map observation rows → feature matrix (list of rows) + prefix keys.

    Pure: no scikit-learn, no I/O. The returned key list is
    ``"<prefix>@AS<origin>"`` so callers can join scores back to
    observations. Malformed prefixes get neutral geometric features but
    still produce a row (never dropped).
    """
    # Index announced networks → set of origins, for MOAS + sub-prefix
    # conflict lookups. Both are O(rows · 32) not O(rows²).
    _Net = ipaddress.IPv4Network | ipaddress.IPv6Network
    moas: dict[str, int] = {}
    netmap: dict[_Net, set[int]] = {}
    parsed: list[_Net | None] = []
    for r in rows:
        moas[r.prefix] = moas.get(r.prefix, 0) + 1
        try:
            net = ipaddress.ip_network(r.prefix)
        except ValueError:
            net = None
        parsed.append(net)
        if net is not None:
            netmap.setdefault(net, set()).add(r.origin_as)

    matrix: list[list[float]] = []
    keys: list[str] = []
    for i, r in enumerate(rows):
        net = parsed[i]
        sub_conflict = 0
        plen = _mask_len(r.prefix)
        if net is not None:
            for shorter in range(net.prefixlen - 1, 7, -1):
                sup = net.supernet(new_prefix=shorter)
                if sup in netmap and (netmap[sup] - {r.origin_as}):
                    sub_conflict = 1
                    break
        matrix.append(
            [
                float(plen),
                1.0 if plen == 24 else 0.0,
                float(moas[r.prefix]),
                float(sub_conflict),
                float(r.n_peers),
                float(r.n_paths),
                float(r.mean_path_len),
                float(r.min_path_len),
            ]
        )
        keys.append(f"{r.prefix}@AS{r.origin_as}")
    return matrix, keys


def _mask_len(prefix: str) -> int:
    if "/" not in prefix:
        return 0
    try:
        return int(prefix.rsplit("/", 1)[1])
    except ValueError:
        return 0


@dataclass(slots=True)
class RankingEval:
    """Ranking-quality summary for a rare-event anomaly scorer."""

    n: int
    n_positive: int
    base_rate: float
    average_precision: float

    @property
    def lift(self) -> float:
        """Average precision relative to the random-ranking baseline (= base rate)."""
        if self.base_rate <= 0:
            return 0.0
        return self.average_precision / self.base_rate


def evaluate_ranking(scores: list[float], labels: list[int]) -> RankingEval:
    """Average-precision + lift of ``scores`` against binary ``labels``.

    Uses scikit-learn's ``average_precision_score`` (area under the
    precision-recall curve). Imported lazily so the function is only a
    hard dependency for callers that actually evaluate.
    """
    from sklearn.metrics import average_precision_score

    n = len(labels)
    n_pos = sum(labels)
    base = n_pos / n if n else 0.0
    ap = float(average_precision_score(labels, scores)) if n_pos and n_pos < n else 0.0
    return RankingEval(n=n, n_positive=n_pos, base_rate=base, average_precision=ap)


def score_isolation_forest(
    matrix: list[list[float]],
    *,
    n_estimators: int = 300,
    random_state: int = 0,
) -> list[float]:
    """Fit an Isolation Forest and return per-row anomaly scores (higher = more anomalous).

    Unsupervised: the model never sees labels. Lazy scikit-learn import.
    """
    import numpy as np
    from sklearn.ensemble import IsolationForest

    x = np.asarray(matrix, dtype=float)
    model = IsolationForest(n_estimators=n_estimators, random_state=random_state)
    model.fit(x)
    # score_samples: higher = more normal; negate so higher = more anomalous.
    return [float(-s) for s in model.score_samples(x)]
