"""NetPulse CLI entry point."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    name="netpulse",
    help="Multi-signal Internet outage and BGP anomaly detector.",
    no_args_is_help=True,
)

ingest_app = typer.Typer(help="Pull data from external sources into local storage.")
app.add_typer(ingest_app, name="ingest")

detect_app = typer.Typer(help="Run detectors over stored signals.")
app.add_typer(detect_app, name="detect")

benchmark_app = typer.Typer(help="Replay labeled historical incidents.")
app.add_typer(benchmark_app, name="benchmark")

console = Console()


_DURATION_RE = re.compile(r"^(\d+)([hms])$")


def _parse_duration_to_us(duration: str) -> int:
    """Parse durations like '1h', '30m', '5s' into microseconds."""
    match = _DURATION_RE.match(duration.strip())
    if match is None:
        raise typer.BadParameter(f"duration {duration!r} must look like '1h', '30m', or '5s'.")
    value = int(match.group(1))
    unit = match.group(2)
    seconds = {"h": 3600, "m": 60, "s": 1}[unit] * value
    return seconds * 1_000_000


def _parse_iso_to_us(value: str) -> int:
    """Parse an ISO-8601 datetime (naive treated as UTC) into microseconds since epoch."""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as e:
        raise typer.BadParameter(
            f"start {value!r} must be ISO-8601, e.g. 2024-01-01T00:00:00."
        ) from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000)


@ingest_app.command("bgp")
def ingest_bgp(
    start: Annotated[
        str,
        typer.Option(
            "--start",
            help="ISO-8601 start time, UTC if no offset (e.g. 2024-01-01T00:00:00).",
        ),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", help="Path to the DuckDB file to write into."),
    ],
    collector: Annotated[
        str,
        typer.Option("--collector", help="RIPE RIS or RouteViews collector name."),
    ] = "rrc00",
    duration: Annotated[
        str,
        typer.Option("--duration", help="Window length: '1h', '30m', '5s'."),
    ] = "1h",
) -> None:
    """Pull a window of BGP updates from a collector into a DuckDB store."""
    from netpulse.ingest.bgp import pull_bgp_window
    from netpulse.storage.duckdb_store import BGPStore

    start_us = _parse_iso_to_us(start)
    end_us = start_us + _parse_duration_to_us(duration)

    out.parent.mkdir(parents=True, exist_ok=True)

    console.log(
        f"Pulling BGP updates from collector={collector} "
        f"start_us={start_us} end_us={end_us} -> {out}"
    )
    store = BGPStore(out)
    try:
        count = pull_bgp_window(collector, start_us, end_us, store)
    finally:
        store.close()
    console.log(f"Wrote {count} BGP records.")


@detect_app.command("bgp")
def detect_bgp(
    in_path: Annotated[
        Path,
        typer.Option("--in", help="Path to the BGP DuckDB store."),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="ISO-8601 window start, UTC if no offset."),
    ],
    duration: Annotated[
        str,
        typer.Option("--duration", help="Window length: '5m', '1h', etc."),
    ] = "5m",
    min_announce_count: Annotated[
        int,
        typer.Option(
            "--min-announce-count",
            help="MOAS threshold: skip prefixes seen fewer than N times in the window.",
        ),
    ] = 1,
) -> None:
    """Run BGP detectors over a window of stored data and print alerts."""
    from netpulse.alerts.publishers import StdoutPublisher
    from netpulse.detectors.moas import MOASDetector
    from netpulse.features.bgp import extract_bgp_features
    from netpulse.storage.duckdb_store import BGPStore

    start_us = _parse_iso_to_us(start)
    end_us = start_us + _parse_duration_to_us(duration)

    store = BGPStore(in_path)
    try:
        features = extract_bgp_features(store, start_us, end_us)
    finally:
        store.close()

    publisher = StdoutPublisher(console=console)
    detectors = [MOASDetector(min_announce_count=min_announce_count)]
    total_alerts = 0
    for det in detectors:
        total_alerts += publisher.publish_all(det.score(features))

    console.log(
        f"window={start_us}-{end_us} "
        f"announces={features.announce_total} "
        f"withdraws={features.withdraw_total} "
        f"alerts={total_alerts}"
    )


@benchmark_app.command("replay")
def benchmark_replay(
    incidents_dir: Annotated[
        Path,
        typer.Option(
            "--incidents",
            help="Directory of incident JSON files (see data/incidents/_README.md).",
        ),
    ],
    store_path: Annotated[
        Path,
        typer.Option(
            "--store",
            help="Path to a populated BGP DuckDB store covering the incident windows.",
        ),
    ],
    chunk: Annotated[
        str,
        typer.Option("--chunk", help="Sub-window length used to approximate latency."),
    ] = "1m",
) -> None:
    """Replay every incident in the directory through the BGP detectors."""
    from netpulse.benchmark.loader import load_incidents
    from netpulse.benchmark.metrics import summarize
    from netpulse.benchmark.replay import replay_bgp_incident
    from netpulse.detectors.moas import MOASDetector
    from netpulse.storage.duckdb_store import BGPStore

    chunk_us = _parse_duration_to_us(chunk)
    incidents = load_incidents(incidents_dir)
    if not incidents:
        console.log(f"No incidents found in {incidents_dir}.")
        raise typer.Exit(code=1)

    detectors = [MOASDetector()]
    results = []
    store = BGPStore(store_path)
    try:
        for inc in incidents:
            result = replay_bgp_incident(inc, store, detectors, chunk_us=chunk_us)
            status = "DETECTED" if result.detected else "missed"
            latency = (
                f"{result.latency_us / 1_000_000:.1f}s" if result.latency_us is not None else "n/a"
            )
            console.log(f"{inc.id}: {status} (latency={latency}, alerts={len(result.alerts)})")
            results.append(result)
    finally:
        store.close()

    summary = summarize(results)
    console.log(
        f"summary: {summary.detected_count}/{summary.total_incidents} detected "
        f"(rate={summary.detection_rate:.2%}); "
        f"mean_latency_us={summary.mean_latency_us}; "
        f"median_latency_us={summary.median_latency_us}"
    )


@app.command("serve")
def serve() -> None:
    """Serve the alerts API and dashboard (not implemented yet)."""
    console.print("[yellow]serve: not implemented yet[/]")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
