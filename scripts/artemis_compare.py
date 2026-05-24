"""Compare NetPulse alerts against an ARTEMIS run on the same incident.

Pipeline:
1. NetPulse alerts come from ``scripts/run_corpus_benchmark.py``'s
   ``docs/corpus_benchmark.json`` -- one row per incident.
2. ARTEMIS hijacks are extracted via its REST API (``GET /api/hijacks``)
   or via a raw Postgres dump from the ``view_hijacks`` table. Either
   way the input is a list of hijack rows; this script normalizes them
   and lines them up against the NetPulse row.

Run after you have both halves:

    uv run python scripts/artemis_compare.py \\
        --netpulse docs/corpus_benchmark.json \\
        --artemis docs/artemis/results/raw/*.json \\
        --out docs/artemis/comparison.json

The output JSON is consumed by ``scripts/artemis_aggregate.py`` (not in
this initial scaffold) to render the head-to-head table that ships in
``docs/artemis-comparison.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class HeadToHeadRow:
    incident_id: str
    netpulse_outcome: str  # "TP" | "FN" | "GAP" | "MISSING"
    netpulse_on_target: int
    netpulse_other: int
    artemis_fired: bool
    artemis_alerts: int
    artemis_hijack_types: list[str]
    notes: str = ""


def _load_netpulse_rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"netpulse benchmark file not found: {path}")
    blob = json.loads(path.read_text())
    return {r["incident_id"]: r for r in blob["results"]}


def _load_artemis_rows(paths: list[Path]) -> dict[str, list[dict]]:
    """ARTEMIS hijacks are grouped per file (one file per incident replay).

    The filename's stem must match the incident id (e.g.
    ``youtube_pakistan_2008.json`` -> ``youtube_pakistan_2008``).
    Each file is the JSON list returned by GET /api/hijacks for the
    relevant time window.
    """
    out: dict[str, list[dict]] = {}
    for p in paths:
        if not p.exists():
            continue
        rows = json.loads(p.read_text())
        if not isinstance(rows, list):
            raise SystemExit(f"{p}: expected a list of hijack rows")
        out[p.stem] = rows
    return out


def _summarize_artemis(rows: list[dict]) -> tuple[bool, int, list[str]]:
    if not rows:
        return (False, 0, [])
    types = sorted({r.get("hijack_type") or r.get("type") or "?" for r in rows})
    return (True, len(rows), types)


def compare(netpulse_path: Path, artemis_paths: list[Path]) -> list[HeadToHeadRow]:
    np_rows = _load_netpulse_rows(netpulse_path)
    ar_rows = _load_artemis_rows(artemis_paths)

    incident_ids = sorted(set(np_rows) | set(ar_rows))
    out: list[HeadToHeadRow] = []
    for inc_id in incident_ids:
        np_row = np_rows.get(inc_id)
        artemis_rows_for_inc = ar_rows.get(inc_id, [])
        artemis_fired, artemis_alerts, artemis_types = _summarize_artemis(
            artemis_rows_for_inc
        )

        if np_row is None:
            out.append(
                HeadToHeadRow(
                    incident_id=inc_id,
                    netpulse_outcome="MISSING",
                    netpulse_on_target=0,
                    netpulse_other=0,
                    artemis_fired=artemis_fired,
                    artemis_alerts=artemis_alerts,
                    artemis_hijack_types=artemis_types,
                    notes="present in ARTEMIS output but not in NetPulse corpus benchmark",
                )
            )
            continue

        out.append(
            HeadToHeadRow(
                incident_id=inc_id,
                netpulse_outcome=np_row["outcome"],
                netpulse_on_target=int(np_row.get("on_target_alerts", 0)),
                netpulse_other=int(np_row.get("other_alerts", 0)),
                artemis_fired=artemis_fired,
                artemis_alerts=artemis_alerts,
                artemis_hijack_types=artemis_types,
                notes=(
                    ""
                    if artemis_rows_for_inc or np_row["outcome"] == "GAP"
                    else "no ARTEMIS replay result yet; see docs/artemis-comparison-plan.md"
                ),
            )
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--netpulse",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "docs"
        / "corpus_benchmark.json",
        help="Path to NetPulse corpus benchmark JSON.",
    )
    ap.add_argument(
        "--artemis",
        type=Path,
        nargs="*",
        default=[],
        help="ARTEMIS hijack dump JSON files (one per incident).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to stdout.",
    )
    args = ap.parse_args()

    rows = compare(args.netpulse, args.artemis)
    blob = {"rows": [asdict(r) for r in rows]}
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(blob, indent=2))
        print(f"wrote {len(rows)} comparison row(s) -> {args.out}")
    else:
        json.dump(blob, sys.stdout, indent=2)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
