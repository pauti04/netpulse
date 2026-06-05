# Unsupervised anomaly detection (`netpulse.ml`)

**Question.** The rule-based detectors need a *baseline* (a RIB snapshot of
legitimate origins) to flag a hijack. Can the hijacked announcements be
surfaced from **observable features alone** — no labels, no ground-truth
origins, no baseline?

**Approach.** An Isolation Forest over 8 scale-invariant per-(prefix, origin)
features, evaluated as a **ranking** problem against held-out ground truth
(does the model score the known-anomalous announcements above benign ones?).
The model is fully unsupervised — it never sees labels.

## Result

Evaluated on two real incident windows pulled unfiltered from RIPE RIS
`rrc00` (37,269 observations total):

| Incident | Observations | Anomaly base rate | Isolation Forest AP | Lift vs random | Single-rule baseline AP |
| -------- | -----------: | ----------------: | ------------------: | -------------: | ----------------------: |
| Indosat 2014    | 33,034 | 11.0% | **0.34** | **3.1×** | 0.18 |
| Rostelecom 2017 |  4,235 |  3.1% | **0.48** | **15.6×** | 0.04 |

The learned scorer beats the single-feature rule baseline (rank by
sub-prefix conflict alone) on both incidents, and surfaces hijacks
3–16× better than random ranking — with **no labels and no baseline**.

`docs/ml_eval.json` holds the machine-readable result.

## Honest caveats

- **Why unsupervised, not a supervised classifier?** A supervised model on
  "is this the culprit AS" trivially hits AUC ≈ 1.0 by learning *origin
  volume* — the culprit is simply the biggest announcer in these
  incidents. That is **label leakage**, not detection skill; removing the
  volume feature collapses cross-incident transfer to ~0. The unsupervised
  ranking framing avoids the leakage and reports a metric that means
  something on a 3–11% positive rate (average precision + lift, not
  accuracy). Recognizing and refusing the leaky 1.0 is the point.
- **Scale-invariant features only.** No raw "prefixes-per-origin" count, for
  the leakage reason above.
- **Two incidents.** This is a proof-of-concept on the corpus's two
  unfiltered windows, not a production model.

## Reproduce

The 8-feature table is committed (`data/ml/hijack_features.parquet`, ~640 KB)
so the eval runs with no network:

```sh
uv sync --extra ml
uv run python scripts/ml_anomaly_eval.py
```

To rebuild the feature table from scratch, first fetch the two unfiltered
windows (requires the `[bgp]` extra + libBGPStream), then rebuild:

```sh
uv run netpulse ingest bgp --start 2014-04-02T18:25:00 --duration 10m \
    --collector rrc00 --out data/ml/indosat_2014_unfiltered.duckdb
uv run netpulse ingest bgp --start 2017-04-26T22:36:00 --duration 8m \
    --collector rrc00 --out data/ml/rostelecom_2017_unfiltered.duckdb
uv run --extra ml python scripts/build_ml_dataset.py
```
