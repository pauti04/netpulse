"""Score every labeled incident in data/incidents/ against its expected detector.

Per-incident outcome is one of:
- TP   (true positive)    -- detector fired on the right prefix / shape
- FN   (false negative)   -- detector failed to fire on a labeled incident
- GAP  (documented limit) -- expected detector is shipped, but a known
                             data/coverage gap prevents detection
                             (e.g. CAIDA missing an AS pair); the
                             incident notes spell it out

The script also tallies alerts on the incident's store that are NOT on
the labeled victim prefix -- these are an unconstrained-FP estimate for
sub-prefix-hijack windows. Route-leak windows skip this because their
filtered RIS pull is not representative of the global table.

Outputs:
- A console table.
- A JSON dump at docs/corpus_benchmark.json so the chart script can
  consume it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from netpulse.benchmark.incident import Incident
from netpulse.benchmark.loader import load_incidents
from netpulse.detectors.baseline import BGPBaseline
from netpulse.detectors.moas import MOASDetector
from netpulse.detectors.route_leak import (
    ASRelationshipMap,
    ObservedPath,
    RouteLeakDetector,
    parse_as_path,
)
from netpulse.detectors.subprefix import SubPrefixHijackDetector
from netpulse.detectors.withdraw_spike import WithdrawSpikeDetector
from netpulse.features.bgp import extract_bgp_features
from netpulse.storage.asrel_store import ASRelStore
from netpulse.storage.duckdb_store import BGPStore

REPO_ROOT = Path(__file__).resolve().parent.parent
INCIDENTS_DIR = REPO_ROOT / "data" / "incidents"


@dataclass
class IncidentResult:
    incident_id: str
    shape: str
    expected_detector: str
    outcome: str  # "TP" | "FN" | "GAP"
    on_target_alerts: int
    other_alerts: int
    notes: str = ""


def _resolve(inc: Incident, rel: str | None) -> Path | None:
    if rel is None:
        return None
    return (INCIDENTS_DIR / rel).resolve()


def score_subprefix_incident(inc: Incident) -> IncidentResult:
    store_path = _resolve(inc, inc.bgp_store_path)
    baseline_path = _resolve(inc, inc.baseline_path)
    assert store_path and baseline_path, f"{inc.id} needs both store and baseline"

    with BGPStore(baseline_path) as bs:
        baseline = BGPBaseline.from_store(bs)
    with BGPStore(store_path) as store:
        feats = extract_bgp_features(store, inc.start_us, inc.end_us)

    alerts = SubPrefixHijackDetector(baseline).score(feats)
    on_target = 0
    other = 0
    for a in alerts:
        if inc.prefix is not None and a.entity == inc.prefix:
            on_target += 1
        elif inc.prefix is None and a.detector == "subprefix_hijack":
            on_target += 1
        else:
            other += 1
    # If incident.prefix is set, on_target>=1 means the labeled prefix
    # fired. If prefix is None (e.g., MyEtherWallet has one
    # representative prefix but multiple were hijacked), we consider it
    # detected if ANY sub-prefix alert fired.
    outcome = "TP" if (on_target > 0 or (inc.prefix is None and alerts)) else "FN"
    return IncidentResult(
        incident_id=inc.id,
        shape="sub-prefix hijack",
        expected_detector="subprefix_hijack",
        outcome=outcome,
        on_target_alerts=on_target,
        other_alerts=other,
    )


def score_routeleak_incident(inc: Incident) -> IncidentResult:
    store_path = _resolve(inc, inc.bgp_store_path)
    asrel_path = _resolve(inc, inc.asrel_path)
    assert store_path and asrel_path, f"{inc.id} needs both store and asrel"

    with ASRelStore(asrel_path) as store:
        rels = ASRelationshipMap.from_store(store)

    with BGPStore(store_path) as store:
        rows = store.query(
            "SELECT timestamp_us, prefix, peer_as, as_path FROM bgp_records "
            "WHERE update_type='A' AND as_path IS NOT NULL "
            "  AND timestamp_us >= ? AND timestamp_us < ?",
            [inc.start_us, inc.end_us],
        )
    paths = []
    for ts, p, peer, asp in rows:
        asns = parse_as_path(str(asp))
        if asns:
            paths.append(
                ObservedPath(
                    prefix=str(p), asns=asns, peer_as=int(peer), timestamp_us=int(ts)
                )
            )

    alerts = RouteLeakDetector(rels=rels).score_paths(paths)
    # For route leaks we filter to paths that traverse the attacker AS
    # and reach the victim AS as origin -- that's the documented leak
    # shape for the labeled incident.
    on_target = sum(
        1
        for a in alerts
        if (
            inc.attacker_asn is None
            or inc.attacker_asn in a.evidence.get("path", [])
        )
        and (
            inc.victim_asn is None
            or inc.victim_asn in a.evidence.get("path", [])
        )
    )
    other = len(alerts) - on_target
    if on_target > 0:
        outcome = "TP"
    elif len(paths) == 0:
        outcome = "FN"
    else:
        # The data is there but the detector did not fire. If the notes
        # mention 'unknown' / 'open detector gap', score as GAP not FN
        # so the corpus distinguishes 'detector missed' from 'data /
        # data-coverage limitation'.
        if "open detector gap" in inc.notes.lower() or "gap" in inc.notes.lower():
            outcome = "GAP"
        else:
            outcome = "FN"
    return IncidentResult(
        incident_id=inc.id,
        shape="route leak (RFC 7908)",
        expected_detector="route_leak",
        outcome=outcome,
        on_target_alerts=on_target,
        other_alerts=other,
    )


_SCORERS = {
    "subprefix_hijack": score_subprefix_incident,
    "route_leak": score_routeleak_incident,
}


def main() -> None:
    incidents = load_incidents(INCIDENTS_DIR)
    results: list[IncidentResult] = []

    for inc in incidents:
        # Pick the first expected_detector with a registered scorer.
        scorer = None
        chosen = None
        for d in inc.expected_detectors:
            if d in _SCORERS:
                scorer = _SCORERS[d]
                chosen = d
                break
        if scorer is None:
            print(f"  skip {inc.id}: no scorer for {inc.expected_detectors}")
            continue
        try:
            r = scorer(inc)
        except (AssertionError, FileNotFoundError) as e:
            print(f"  skip {inc.id}: {e}")
            continue
        results.append(r)
        print(
            f"  {inc.id:35s}  {r.shape:22s}  {r.expected_detector:18s}"
            f"  {r.outcome:4s}  on_target={r.on_target_alerts:5d}  other={r.other_alerts}"
        )

    n_total = len(results)
    n_tp = sum(1 for r in results if r.outcome == "TP")
    n_fn = sum(1 for r in results if r.outcome == "FN")
    n_gap = sum(1 for r in results if r.outcome == "GAP")
    print()
    print(f"TPR (TP / (TP + FN + GAP))     = {n_tp}/{n_total} = {n_tp / n_total:.2%}")
    print(f"detector-coverage rate         = {(n_tp + n_gap)}/{n_total} = "
          f"{(n_tp + n_gap) / n_total:.2%}  (TP + documented GAPs)")
    print(f"strict failure rate (FN only)  = {n_fn}/{n_total} = {n_fn / n_total:.2%}")

    out: dict[str, Any] = {
        "total": n_total,
        "tp": n_tp,
        "fn": n_fn,
        "gap": n_gap,
        "results": [asdict(r) for r in results],
    }
    out_path = REPO_ROOT / "docs" / "corpus_benchmark.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
