"""NetPulse CLI entry point."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

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
    record_type: Annotated[
        str,
        typer.Option(
            "--record-type",
            help="'updates' (announces+withdraws) or 'ribs' (RIB snapshots).",
        ),
    ] = "updates",
    filter_str: Annotated[
        str | None,
        typer.Option(
            "--filter",
            help=(
                "libBGPStream filter (e.g. 'prefix any 1.1.1.0/24'). Native "
                "filtering is many times faster than no filter."
            ),
        ),
    ] = None,
) -> None:
    """Pull a window of BGP records from a collector into a DuckDB store."""
    from netpulse.ingest.bgp import pull_bgp_window
    from netpulse.storage.duckdb_store import BGPStore

    if record_type not in ("updates", "ribs"):
        raise typer.BadParameter("--record-type must be 'updates' or 'ribs'")

    start_us = _parse_iso_to_us(start)
    end_us = start_us + _parse_duration_to_us(duration)

    out.parent.mkdir(parents=True, exist_ok=True)

    console.log(
        f"Pulling collector={collector} record_type={record_type} "
        f"start_us={start_us} end_us={end_us} filter={filter_str!r} -> {out}"
    )
    store = BGPStore(out)
    try:
        count = pull_bgp_window(
            collector,
            start_us,
            end_us,
            store,
            record_type=record_type,
            filter_str=filter_str,
        )
    finally:
        store.close()
    console.log(f"Wrote {count} BGP records.")


@ingest_app.command("asrel")
def ingest_asrel(
    out: Annotated[
        Path,
        typer.Option("--out", help="Path to the AS-relationships DuckDB store."),
    ],
    source: Annotated[
        str | None,
        typer.Option(
            "--source",
            help="CAIDA serial-2 URL. Defaults to the current month's snapshot.",
        ),
    ] = None,
) -> None:
    """Pull CAIDA serial-2 inferred AS relationships into a DuckDB store."""
    from netpulse.ingest.asrel import pull_caida_relationships
    from netpulse.storage.asrel_store import ASRelStore

    out.parent.mkdir(parents=True, exist_ok=True)
    console.log(f"Pulling AS relationships from CAIDA -> {out}")
    store = ASRelStore(out)
    try:
        n = pull_caida_relationships(store, source_url=source)
    finally:
        store.close()
    console.log(f"Wrote {n} AS relationships.")


@ingest_app.command("rpki")
def ingest_rpki(
    out: Annotated[
        Path,
        typer.Option("--out", help="Path to write the RPKI DuckDB store."),
    ],
    source: Annotated[
        str,
        typer.Option(
            "--source",
            help="rpki-client JSON URL. Default: Cloudflare's public feed.",
        ),
    ] = "https://rpki.cloudflare.com/rpki.json",
) -> None:
    """Pull a snapshot of RPKI Validated ROA Payloads into a DuckDB store."""
    from netpulse.ingest.rpki import pull_rpki_snapshot
    from netpulse.storage.rpki_store import RPKIStore

    out.parent.mkdir(parents=True, exist_ok=True)
    console.log(f"Pulling RPKI VRPs from {source} -> {out}")
    store = RPKIStore(out)
    try:
        n = pull_rpki_snapshot(store, source_url=source)
    finally:
        store.close()
    console.log(f"Wrote {n} RPKI VRPs.")


@ingest_app.command("dns")
def ingest_dns(
    out: Annotated[
        Path,
        typer.Option("--out", help="Path to the DNS probe DuckDB store."),
    ],
    hostnames: Annotated[
        str,
        typer.Option(
            "--hostnames",
            help="Comma-separated list of hostnames to query.",
        ),
    ],
    resolvers: Annotated[
        str,
        typer.Option(
            "--resolvers",
            help="Comma-separated list of resolver IPs.",
        ),
    ] = "1.1.1.1,8.8.8.8",
    interval: Annotated[
        str,
        typer.Option("--interval", help="Seconds between probe rounds: '5s', '1m', etc."),
    ] = "60s",
    duration: Annotated[
        str,
        typer.Option("--duration", help="Total probing duration: '5m', '1h', etc."),
    ] = "5m",
    qtype: Annotated[
        str,
        typer.Option("--qtype", help="DNS query type."),
    ] = "A",
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Per-query timeout in seconds."),
    ] = 2.0,
) -> None:
    """Run an active DNS probe loop and store the results.

    Queries each (hostname, resolver) pair every ``--interval`` for the
    configured ``--duration``, then exits. Records carry success / error
    / response-time so the detector can score failure-rate jumps later.
    """
    from netpulse.ingest.dns import run_probe_loop
    from netpulse.storage.dns_store import DNSProbeStore

    host_list = [h.strip() for h in hostnames.split(",") if h.strip()]
    resolver_list = [r.strip() for r in resolvers.split(",") if r.strip()]
    if not host_list or not resolver_list:
        raise typer.BadParameter("at least one hostname and one resolver are required")

    interval_s = _parse_duration_to_us(interval) / 1_000_000
    duration_s = _parse_duration_to_us(duration) / 1_000_000

    out.parent.mkdir(parents=True, exist_ok=True)
    console.log(
        f"DNS probes -> {out}  "
        f"hostnames={len(host_list)} resolvers={len(resolver_list)} "
        f"interval={interval} duration={duration}"
    )
    with DNSProbeStore(out) as store:
        n = run_probe_loop(
            store,
            hostnames=host_list,
            resolvers=resolver_list,
            interval_s=interval_s,
            duration_s=duration_s,
            qtype=qtype,
            timeout_s=timeout,
        )
    console.log(f"Wrote {n} DNS probe records.")


@detect_app.command("dns")
def detect_dns(
    in_path: Annotated[
        Path,
        typer.Option("--in", help="Path to the DNS probe DuckDB store."),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="ISO-8601 window start, UTC if no offset."),
    ],
    duration: Annotated[
        str,
        typer.Option("--duration", help="Window length: '5m', '1h', etc."),
    ] = "5m",
    failure_rate: Annotated[
        float,
        typer.Option("--failure-rate", help="Per-hostname failure-rate threshold (0..1)."),
    ] = 0.5,
    min_probes: Annotated[
        int,
        typer.Option("--min-probes", help="Minimum probes per hostname to evaluate."),
    ] = 4,
) -> None:
    """Run the DNS reachability detector over stored probe results."""
    from netpulse.alerts.publishers import StdoutPublisher
    from netpulse.detectors.dns_failure import DNSFailureRateDetector
    from netpulse.features.dns import extract_dns_features
    from netpulse.storage.dns_store import DNSProbeStore

    start_us = _parse_iso_to_us(start)
    end_us = start_us + _parse_duration_to_us(duration)

    with DNSProbeStore(in_path) as store:
        feats = extract_dns_features(store, start_us, end_us)

    detector = DNSFailureRateDetector(failure_rate_threshold=failure_rate, min_probes=min_probes)
    publisher = StdoutPublisher(console=console)
    n = publisher.publish_all(detector.score(feats))
    console.log(
        f"window={start_us}-{end_us} n_total={feats.n_total} "
        f"n_failure={feats.n_failure} "
        f"failure_rate={feats.overall_failure_rate:.2%} alerts={n}"
    )


@detect_app.command("leak")
def detect_leak(
    in_path: Annotated[
        Path,
        typer.Option("--in", help="Path to the BGP DuckDB store."),
    ],
    asrel_path: Annotated[
        Path,
        typer.Option(
            "--asrel",
            help="Path to an AS-relationships DuckDB store (e.g. CAIDA serial-2).",
        ),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="ISO-8601 window start, UTC if no offset."),
    ],
    duration: Annotated[
        str,
        typer.Option("--duration", help="Window length: '5m', '1h', etc."),
    ] = "5m",
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help=(
                "Detection mode: 'valley' (pairwise valley-free, default), "
                "'cone' (customer-cone-aware), or 'both'."
            ),
        ),
    ] = "valley",
) -> None:
    """Run a route-leak detector over stored BGP records.

    Two algorithms are available against the same input and AS-relationships
    data: bilateral valley-free (RFC 7908 §3.1) and customer-cone-aware. The
    cone variant catches paths the pair-direction check misses when adjacent
    relationships are sparse; see ``docs/paper.md`` §7.
    """
    from netpulse.alerts.publishers import StdoutPublisher
    from netpulse.detectors.customer_cone import CustomerConeMap
    from netpulse.detectors.customer_cone_leak import CustomerConeLeakDetector
    from netpulse.detectors.route_leak import (
        ASRelationshipMap,
        ObservedPath,
        RouteLeakDetector,
        parse_as_path,
    )
    from netpulse.storage.asrel_store import ASRelStore
    from netpulse.storage.duckdb_store import BGPStore

    if mode not in {"valley", "cone", "both"}:
        raise typer.BadParameter("--mode must be 'valley', 'cone', or 'both'")

    start_us = _parse_iso_to_us(start)
    end_us = start_us + _parse_duration_to_us(duration)

    asrel_store = ASRelStore(asrel_path)
    try:
        rels = ASRelationshipMap.from_store(asrel_store)
    finally:
        asrel_store.close()
    console.log(f"loaded AS-relationships: {len(rels.pairs)} ordered pairs")

    store = BGPStore(in_path)
    try:
        rows = store.query(
            """
            SELECT timestamp_us, prefix, peer_as, as_path
            FROM bgp_records
            WHERE update_type = 'A' AND as_path IS NOT NULL
              AND timestamp_us >= ? AND timestamp_us < ?
            """,
            [start_us, end_us],
        )
    finally:
        store.close()

    paths = []
    skipped_unparseable = 0
    for ts, pfx, peer, asp in rows:
        asns = parse_as_path(str(asp))
        if asns is None:
            skipped_unparseable += 1
            continue
        paths.append(
            ObservedPath(
                prefix=str(pfx),
                asns=asns,
                peer_as=int(peer),
                timestamp_us=int(ts),
            )
        )

    publisher = StdoutPublisher(console=console)
    n = 0
    if mode in {"valley", "both"}:
        n += publisher.publish_all(RouteLeakDetector(rels=rels).score_paths(paths))
    if mode in {"cone", "both"}:
        cones = CustomerConeMap.from_relationships(rels)
        n += publisher.publish_all(CustomerConeLeakDetector(cones=cones).score_paths(paths))
    console.log(
        f"window={start_us}-{end_us} paths={len(paths)} mode={mode} "
        f"unparseable={skipped_unparseable} leak_alerts={n}"
    )


@detect_app.command("rpki")
def detect_rpki(
    in_path: Annotated[
        Path,
        typer.Option("--in", help="Path to the BGP DuckDB store."),
    ],
    rpki_path: Annotated[
        Path,
        typer.Option("--rpki", help="Path to the RPKI VRPs DuckDB store."),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="ISO-8601 window start, UTC if no offset."),
    ],
    duration: Annotated[
        str,
        typer.Option("--duration", help="Window length: '5m', '1h', etc."),
    ] = "5m",
) -> None:
    """Run RPKI Origin Validation over a window of stored BGP records."""
    from netpulse.alerts.publishers import StdoutPublisher
    from netpulse.detectors.rpki import RPKIInvalidDetector, RPKIValidator
    from netpulse.features.bgp import extract_bgp_features
    from netpulse.storage.duckdb_store import BGPStore
    from netpulse.storage.rpki_store import RPKIStore

    start_us = _parse_iso_to_us(start)
    end_us = start_us + _parse_duration_to_us(duration)

    rpki_store = RPKIStore(rpki_path)
    try:
        validator = RPKIValidator.from_store(rpki_store)
    finally:
        rpki_store.close()
    console.log(f"loaded RPKI: {len(validator.by_prefix_v4) + len(validator.by_prefix_v6)} VRPs")

    store = BGPStore(in_path)
    try:
        features = extract_bgp_features(store, start_us, end_us)
    finally:
        store.close()

    publisher = StdoutPublisher(console=console)
    n = publisher.publish_all(RPKIInvalidDetector(validator).score(features))

    console.log(
        f"window={start_us}-{end_us} announces={features.announce_total} "
        f"prefixes={len(features.origins_by_prefix)} rpki_invalid_alerts={n}"
    )


@ingest_app.command("atlas")
def ingest_atlas(
    msm_id: Annotated[
        int,
        typer.Option("--msm", help="RIPE Atlas measurement ID (e.g. 1001)."),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="ISO-8601 window start, UTC if no offset."),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", help="Path to the Atlas DuckDB store."),
    ],
    duration: Annotated[
        str,
        typer.Option("--duration", help="Window length: '5m', '1h', etc."),
    ] = "5m",
) -> None:
    """Pull a window of RIPE Atlas ping results into a DuckDB store."""
    from netpulse.ingest.atlas import pull_atlas_ping_window
    from netpulse.storage.atlas_store import AtlasPingStore

    start_us = _parse_iso_to_us(start)
    end_us = start_us + _parse_duration_to_us(duration)

    out.parent.mkdir(parents=True, exist_ok=True)
    console.log(f"Pulling Atlas msm={msm_id} start_us={start_us} end_us={end_us} -> {out}")
    store = AtlasPingStore(out)
    try:
        n = pull_atlas_ping_window(msm_id, start_us, end_us, store)
    finally:
        store.close()
    console.log(f"Wrote {n} Atlas ping records.")


@detect_app.command("atlas")
def detect_atlas(
    in_path: Annotated[
        Path,
        typer.Option("--in", help="Path to the Atlas DuckDB store."),
    ],
    msm_id: Annotated[
        int,
        typer.Option("--msm", help="Measurement ID to evaluate."),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="ISO-8601 window start, UTC if no offset."),
    ],
    duration: Annotated[
        str,
        typer.Option("--duration", help="Window length: '5m', '1h', etc."),
    ] = "5m",
    threshold: Annotated[
        float,
        typer.Option(
            "--threshold",
            help="Full-loss rate above which the loss-spike detector fires.",
        ),
    ] = 0.20,
) -> None:
    """Run Atlas detectors over a window of stored ping results."""
    from netpulse.alerts.publishers import StdoutPublisher
    from netpulse.detectors.atlas_loss import AtlasLossSpikeDetector
    from netpulse.features.atlas import extract_atlas_features
    from netpulse.storage.atlas_store import AtlasPingStore

    start_us = _parse_iso_to_us(start)
    end_us = start_us + _parse_duration_to_us(duration)

    store = AtlasPingStore(in_path)
    try:
        feats = extract_atlas_features(store, msm_id, start_us, end_us)
    finally:
        store.close()

    publisher = StdoutPublisher(console=console)
    n = publisher.publish_all(
        AtlasLossSpikeDetector(full_loss_rate_threshold=threshold).score(feats)
    )

    console.log(
        f"msm={msm_id} window={start_us}-{end_us} "
        f"results={feats.n_results} full_loss={feats.n_full_loss} "
        f"any_loss_rate={feats.any_loss_rate:.2%} alerts={n}"
    )


@detect_app.command("bgp")
def detect_bgp(
    in_paths: Annotated[
        list[Path],
        typer.Option(
            "--in",
            help=(
                "Path to a BGP DuckDB store. May be repeated to union evidence "
                "across multiple collectors (e.g. `--in rrc00.db --in rrc14.db`)."
            ),
        ),
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
    baseline_path: Annotated[
        Path | None,
        typer.Option(
            "--baseline",
            help="DuckDB store with a RIB baseline; enables the sub-prefix hijack detector.",
        ),
    ] = None,
) -> None:
    """Run BGP detectors over a window of stored data and print alerts.

    With a single ``--in`` this reads that store directly. With multiple
    ``--in`` flags it unions all stores via a read-only DuckDB ATTACH and
    runs the detectors over the union — covers incidents that are visible
    at only a subset of collectors (e.g. the 2024-06-27 Cloudflare event).
    """
    from netpulse.alerts.publishers import StdoutPublisher
    from netpulse.detectors.base import DetectorBase
    from netpulse.detectors.baseline import BGPBaseline
    from netpulse.detectors.moas import MOASDetector
    from netpulse.detectors.subprefix import SubPrefixHijackDetector
    from netpulse.features.bgp import BGPWindowFeatures, extract_bgp_features
    from netpulse.storage.duckdb_store import BGPStore
    from netpulse.storage.multi_store import MultiStoreBGPView

    start_us = _parse_iso_to_us(start)
    end_us = start_us + _parse_duration_to_us(duration)

    if not in_paths:
        raise typer.BadParameter("at least one --in path is required")

    if len(in_paths) == 1:
        with BGPStore(in_paths[0]) as store:
            features = extract_bgp_features(store, start_us, end_us)
    else:
        with MultiStoreBGPView(in_paths) as view:
            for alias, path, n in view.count_by_source():
                console.log(f"{alias}: {Path(path).name} ({n} records)")
            features = extract_bgp_features(view, start_us, end_us)  # type: ignore[arg-type]

    from netpulse.detectors.withdraw_spike import WithdrawSpikeDetector

    detectors: list[DetectorBase[BGPWindowFeatures]] = [
        MOASDetector(min_announce_count=min_announce_count),
        WithdrawSpikeDetector(),
    ]
    if baseline_path is not None:
        baseline_store = BGPStore(baseline_path)
        try:
            baseline = BGPBaseline.from_store(baseline_store)
        finally:
            baseline_store.close()
        console.log(f"loaded baseline: {len(baseline.origins)} prefixes")
        detectors.append(SubPrefixHijackDetector(baseline))

    publisher = StdoutPublisher(console=console)
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
        Path | None,
        typer.Option(
            "--store",
            help=(
                "Fallback BGP DuckDB store. Per-incident 'bgp_store_path' in "
                "the JSON takes precedence."
            ),
        ),
    ] = None,
    chunk: Annotated[
        str,
        typer.Option("--chunk", help="Sub-window length used to approximate latency."),
    ] = "1m",
    baseline_path: Annotated[
        Path | None,
        typer.Option(
            "--baseline",
            help="DuckDB store with a RIB baseline; enables the sub-prefix hijack detector.",
        ),
    ] = None,
) -> None:
    """Replay every incident in the directory through the BGP detectors.

    Each incident may declare its own ``bgp_store_path`` (resolved relative
    to the incident JSON file's directory) so a corpus spanning different
    years can be scored in one command.
    """
    from netpulse.benchmark.loader import load_incidents
    from netpulse.benchmark.metrics import summarize
    from netpulse.benchmark.replay import replay_bgp_incident
    from netpulse.detectors.base import DetectorBase
    from netpulse.detectors.baseline import BGPBaseline
    from netpulse.detectors.moas import MOASDetector
    from netpulse.detectors.subprefix import SubPrefixHijackDetector
    from netpulse.features.bgp import BGPWindowFeatures
    from netpulse.storage.duckdb_store import BGPStore

    chunk_us = _parse_duration_to_us(chunk)
    incidents = load_incidents(incidents_dir)
    if not incidents:
        console.log(f"No incidents found in {incidents_dir}.")
        raise typer.Exit(code=1)

    fallback_baseline: BGPBaseline | None = None
    if baseline_path is not None:
        bs = BGPStore(baseline_path)
        try:
            fallback_baseline = BGPBaseline.from_store(bs)
        finally:
            bs.close()
        console.log(
            f"fallback baseline: {len(fallback_baseline.origins)} prefixes"
            f" from {baseline_path.name}"
        )

    results = []
    incidents_dir_abs = incidents_dir.resolve()
    for inc in incidents:
        if inc.bgp_store_path is not None:
            store_for_inc = (incidents_dir_abs / inc.bgp_store_path).resolve()
        elif store_path is not None:
            store_for_inc = store_path
        else:
            console.log(
                f"{inc.id}: no store specified (no bgp_store_path in JSON, no --store), skipping"
            )
            continue
        if not store_for_inc.exists():
            console.log(f"{inc.id}: store {store_for_inc} not found, skipping")
            continue

        # Per-incident baseline takes precedence; fall back to --baseline.
        baseline_for_inc: BGPBaseline | None = fallback_baseline
        if inc.baseline_path is not None:
            baseline_p = (incidents_dir_abs / inc.baseline_path).resolve()
            if baseline_p.exists():
                bs = BGPStore(baseline_p)
                try:
                    baseline_for_inc = BGPBaseline.from_store(bs)
                finally:
                    bs.close()

        detectors: list[DetectorBase[BGPWindowFeatures]] = [MOASDetector()]
        if baseline_for_inc is not None:
            detectors.append(SubPrefixHijackDetector(baseline_for_inc))

        store = BGPStore(store_for_inc)
        try:
            result = replay_bgp_incident(inc, store, detectors, chunk_us=chunk_us)
        finally:
            store.close()

        status = "DETECTED" if result.detected else "missed"
        latency = (
            f"{result.latency_us / 1_000_000:.1f}s" if result.latency_us is not None else "n/a"
        )
        console.log(
            f"{inc.id}: {status} (store={store_for_inc.name}, "
            f"latency={latency}, alerts={len(result.alerts)})"
        )
        results.append(result)

    summary = summarize(results)
    console.log(
        f"summary: {summary.detected_count}/{summary.total_incidents} detected "
        f"(rate={summary.detection_rate:.2%}); "
        f"mean_latency_us={summary.mean_latency_us}; "
        f"median_latency_us={summary.median_latency_us}"
    )


@benchmark_app.command("stream-latency")
def benchmark_stream_latency(
    incidents_dir: Annotated[
        Path,
        typer.Option(
            "--incidents",
            help="Directory of incident JSON files (see data/incidents/_README.md).",
        ),
    ],
    store_path: Annotated[
        Path | None,
        typer.Option(
            "--store",
            help=(
                "Fallback BGP DuckDB store. Per-incident 'bgp_store_path' in "
                "the JSON takes precedence."
            ),
        ),
    ] = None,
    baseline_path: Annotated[
        Path | None,
        typer.Option(
            "--baseline",
            help="DuckDB store with a RIB baseline (required for the sub-prefix detector).",
        ),
    ] = None,
) -> None:
    """Per-record streaming-mode latency benchmark for the sub-prefix detector.

    Walks records in timestamp order and reports the *microsecond-resolution*
    delta from `incident.onset_us` to the first qualifying detector firing.
    This is the lower bound a real streaming deployment of the same logic
    would achieve, free of the chunk-size ceiling baked into
    `benchmark replay`.
    """
    from netpulse.benchmark.loader import load_incidents
    from netpulse.benchmark.streaming_replay import replay_subprefix_streaming
    from netpulse.detectors.baseline import BGPBaseline
    from netpulse.storage.duckdb_store import BGPStore

    incidents = load_incidents(incidents_dir)
    if not incidents:
        console.log(f"No incidents found in {incidents_dir}.")
        raise typer.Exit(code=1)

    fallback_baseline: BGPBaseline | None = None
    if baseline_path is not None:
        with BGPStore(baseline_path) as bs:
            fallback_baseline = BGPBaseline.from_store(bs)

    incidents_dir_abs = incidents_dir.resolve()
    rows: list[tuple[str, str, str, str]] = []
    for inc in incidents:
        if "subprefix_hijack" not in inc.expected_detectors:
            continue
        if inc.bgp_store_path is not None:
            store_for_inc = (incidents_dir_abs / inc.bgp_store_path).resolve()
        elif store_path is not None:
            store_for_inc = store_path
        else:
            console.log(f"{inc.id}: no store path, skipping")
            continue
        if not store_for_inc.exists():
            console.log(f"{inc.id}: store {store_for_inc} not found, skipping")
            continue

        baseline_for_inc: BGPBaseline | None = fallback_baseline
        if inc.baseline_path is not None:
            baseline_p = (incidents_dir_abs / inc.baseline_path).resolve()
            if baseline_p.exists():
                with BGPStore(baseline_p) as bs:
                    baseline_for_inc = BGPBaseline.from_store(bs)
        if baseline_for_inc is None:
            console.log(f"{inc.id}: no baseline available, skipping")
            continue

        with BGPStore(store_for_inc) as store:
            result = replay_subprefix_streaming(inc, store, baseline_for_inc)

        latency_s = (
            f"{result.latency_from_onset_us / 1_000_000:.3f}s"
            if result.latency_from_onset_us is not None
            else "n/a"
        )
        first_us = (
            str(result.first_detection_record_us)
            if result.first_detection_record_us is not None
            else "n/a"
        )
        rows.append((inc.id, str(result.n_records_scanned), first_us, latency_s))
        status = "DETECTED" if result.detected else "missed"
        console.log(
            f"{inc.id}: {status} "
            f"(scanned={result.n_records_scanned}, "
            f"first_us={first_us}, latency={latency_s})"
        )

    if rows:
        console.log("streaming-mode results:")
        for incident_id, scanned, _first_us, latency_s in rows:
            console.log(f"  {incident_id:40s} scanned={scanned:>8s} latency={latency_s}")


@app.command("stream")
def stream(
    window: Annotated[
        str, typer.Option("--window", help="Rolling window size kept in memory.")
    ] = "1m",
    interval: Annotated[
        str, typer.Option("--interval", help="How often to evaluate detectors.")
    ] = "10s",
    host_filter: Annotated[
        str | None,
        typer.Option("--host", help="Filter to a single RIS collector (e.g. 'rrc03.ripe.net')."),
    ] = None,
    baseline_path: Annotated[
        Path | None,
        typer.Option(
            "--baseline",
            help="Optional sub-prefix baseline DuckDB; enables the sub-prefix detector.",
        ),
    ] = None,
    history_path: Annotated[
        Path | None,
        typer.Option(
            "--history",
            help="Optional alert-history DuckDB; persists every emitted alert for later query.",
        ),
    ] = None,
) -> None:
    """Stream BGP updates from RIS Live, run detectors on a rolling window."""
    from collections import deque

    from netpulse.alerts.publishers import StdoutPublisher
    from netpulse.detectors.base import DetectorBase
    from netpulse.detectors.baseline import BGPBaseline
    from netpulse.detectors.moas import MOASDetector
    from netpulse.detectors.subprefix import SubPrefixHijackDetector
    from netpulse.features.bgp import BGPWindowFeatures
    from netpulse.ingest.stream import StreamUpdate, stream_updates
    from netpulse.storage.duckdb_store import BGPStore

    window_us = _parse_duration_to_us(window)
    interval_us = _parse_duration_to_us(interval)

    detectors: list[DetectorBase[BGPWindowFeatures]] = [MOASDetector()]
    baseline_size: int | None = None
    if baseline_path is not None:
        with BGPStore(baseline_path) as bs:
            baseline = BGPBaseline.from_store(bs)
        baseline_size = len(baseline.origins)
        console.log(f"loaded baseline: {baseline_size} prefixes")
        detectors.append(SubPrefixHijackDetector(baseline))

    from netpulse.alerts.dedup import AlertDeduper
    from netpulse.alerts.publishers import HistoryRecorder, Publisher
    from netpulse.alerts.store import AlertHistoryStore

    publisher: Publisher = StdoutPublisher(console=console)
    history_store: AlertHistoryStore | None = None
    if history_path is not None:
        history_store = AlertHistoryStore(history_path)
        publisher = HistoryRecorder(store=history_store, downstream=publisher)
        console.log(f"recording alerts to {history_path}")
    deduper = AlertDeduper()
    rolling: deque[StreamUpdate] = deque()
    last_check_us = 0
    total_received = 0
    suppressed = 0

    from rich.panel import Panel

    intro_body = (
        f"[bold white]Tapping RIPE RIS Live[/]\n\n"
        f"window=[bold]{window}[/]  ·  evaluate every [bold]{interval}[/]"
        + (f"  ·  host=[bold]{host_filter}[/]" if host_filter else "")
        + (f"  ·  baseline=[bold]{baseline_size}[/] supernets" if baseline_size is not None else "")
        + (f"  ·  history=[bold]{history_path}[/]" if history_path else "")
    )
    console.print(
        Panel(
            intro_body,
            title="[bold cyan]⚡ NetPulse · stream[/]",
            border_style="cyan",
            expand=False,
        )
    )
    console.log(f"connecting to RIS Live (window={window}, interval={interval})...")
    try:
        for upd in stream_updates(host_filter=host_filter):
            rolling.append(upd)
            total_received += 1
            cutoff = upd.timestamp_us - window_us
            while rolling and rolling[0].timestamp_us < cutoff:
                rolling.popleft()

            if upd.timestamp_us - last_check_us < interval_us:
                continue
            last_check_us = upd.timestamp_us

            feats = BGPWindowFeatures(window_start_us=cutoff, window_end_us=upd.timestamp_us)
            for r in rolling:
                if r.update_type == "A":
                    feats.announce_count_by_prefix[r.prefix] = (
                        feats.announce_count_by_prefix.get(r.prefix, 0) + 1
                    )
                    if r.origin_as is not None:
                        feats.origins_by_prefix.setdefault(r.prefix, set()).add(r.origin_as)
                else:
                    feats.withdraw_count_by_prefix[r.prefix] = (
                        feats.withdraw_count_by_prefix.get(r.prefix, 0) + 1
                    )

            n_alerts = 0
            for det in detectors:
                raw_alerts = det.score(feats)
                fresh = list(deduper.filter(raw_alerts))
                suppressed += len(raw_alerts) - len(fresh)
                n_alerts += publisher.publish_all(fresh)

            console.log(
                f"received={total_received} window_updates={len(rolling)} "
                f"prefixes={len(feats.origins_by_prefix)} alerts={n_alerts} "
                f"suppressed_dups={suppressed}"
            )
    except KeyboardInterrupt:
        console.log("stopped by user")
    finally:
        if history_store is not None:
            history_store.close()


# Friendly names for ASes the demo regularly references in hijacker
# paths. Sourced from PeeringDB / public WHOIS; trimmed to operator
# brand (or country + ISP for less-recognizable orgs). Used in the
# AS-path callout to make the chain readable at a glance.
_AS_NAMES: dict[int, str] = {
    # Hijack-case actors
    36561: "YouTube",
    3491: "PCCW",
    3333: "RIPE NCC",
    12859: "BIT",
    6461: "Zayo",
    # Indosat 2014
    4761: "PT Indosat",
    45305: "PT Cyberindo Aditama",
    45348: "PT MyRepublic Indonesia",
    45454: "XL Axiata",
    2914: "NTT",
    9304: "Hutchison Global",
    7713: "Telin (Indosat Singapore)",
    17922: "Telkom Indonesia",
    # MyEtherWallet 2018
    10297: "eNet",
    16509: "Amazon AWS",
    6881: "Petrolink",
    15685: "Edge Web Hosting",
    6939: "Hurricane Electric",
    # Google/NTT 2017
    15169: "Google",
    4713: "NTT OCN",
    701: "Verizon",
    1103: "SURFnet",
    286: "KPN",
    # MainOne/Google 2018
    37282: "MainOne",
    4809: "China Telecom",
    20485: "Transtelecom",
    15562: "Schuberg Philis",
    # Common upstreams
    3549: "Level 3",
    13030: "Init7",
    5408: "GRNET",
    # Vodafone Idea 2024
    55410: "Vodafone Idea",
    9498: "Bharti Airtel",
    45528: "Tata Communications",
    4637: "Telstra Global",
    # Rostelecom 2017
    12389: "Rostelecom",
    1273: "Vodafone",
    26380: "Edgenet (Mastercard)",
    2559: "PSI / USPS",
}


def _as_with_name(asn: int) -> str:
    """Render an AS as 'AS<n> (Name)' if known, else 'AS<n>'."""
    name = _AS_NAMES.get(asn)
    return f"AS{asn} ({name})" if name else f"AS{asn}"


# Curated narratives for the 5 corpus incidents. Each entry pairs a
# story panel with a SQL filter that finds the canonical hijacker AS
# path inside the BGP store, so the demo can show the actual record
# that triggered detection -- not just the alert text. Fixture paths
# are relative to the repo root.
_DEMO_STORIES: dict[str, dict[str, Any]] = {
    "youtube_2008": {
        "incident_type": "hijack",
        "headline": "YouTube /24 sub-prefix hijack",
        "when": "2008-02-24 · 18:47:57 UTC onset",
        "story": (
            "AS17557 announced 208.65.153.0/24 — a more-specific cut out of "
            "YouTube's 208.65.152.0/22 supernet. The announcement was intended "
            "as an internal null-route but leaked to upstream AS3491 (PCCW), "
            "which propagated it globally. For ~two hours, YouTube was "
            "unreachable across the internet."
        ),
        "fixture_rel": "data/fixtures/youtube_2008_demo.duckdb",
        "baseline_rel": None,  # baked into the demo (hand-curated)
        "asrel_rel": None,
        "window_start_us": 1_203_878_700_000_000,
        "window_end_us": 1_203_879_000_000_000,
        "onset_us": 1_203_878_877_000_000,
        "victim": "208.65.152.0/22 → AS36561 (YouTube)",
        "attacker": "AS17557",
        "attacker_asn": 17557,
        "hijack_prefix": "208.65.153.0/24",
        "path_note": (
            "The /24 was intended to stay inside AS17557 as a local null-route. "
            "AS3491 (PCCW) re-announced it globally."
        ),
    },
    "indosat_2014": {
        "incident_type": "hijack",
        "headline": "Indosat / AS4761 MOAS hijack",
        "when": "2014-04-02 · 18:25:31 UTC onset",
        "story": (
            "AS4761 (PT Indosat) briefly re-announced hundreds of thousands of "
            "prefixes outside its 114.4.0.0/15 allocation. RRC00 saw ~3,700 hijacked "
            "prefixes from 16 distinct peers over an 8-minute window. AS45305 "
            "(PT Cyberindo Aditama) was the largest single victim."
        ),
        "fixture_rel": "data/indosat_2014.duckdb",
        "baseline_rel": "data/baselines/indosat_2014_baseline.duckdb",
        "window_start_us": 1_396_462_800_000_000,
        "window_end_us": 1_396_464_000_000_000,
        "onset_us": 1_396_463_131_000_000,
        "victim": "AS45305 (PT Cyberindo Aditama) + ~50 others",
        "attacker": "AS4761 (PT Indosat)",
        "attacker_asn": 4761,
        "hijack_prefix": "103.28.112.0/22",
        "path_note": "AS45305's /22 re-announced with AS4761 spliced in as origin.",
    },
    "myetherwallet_2018": {
        "incident_type": "hijack",
        "headline": "MyEtherWallet / Amazon Route 53 hijack",
        "when": "2018-04-24 · 11:05:50 UTC onset",
        "story": (
            "AS10297 (eNet) announced /24 more-specifics of Amazon Route 53 prefixes "
            "(legitimately covered by AS16509's /23s). DNS resolutions for "
            "myetherwallet.com and other Route 53-served domains were redirected "
            "to attacker-controlled servers; ~$152k in ETH was stolen."
        ),
        "fixture_rel": "data/myetherwallet_2018.duckdb",
        "baseline_rel": "data/baselines/myetherwallet_2018_rib.duckdb",
        "window_start_us": 1_524_567_600_000_000,
        "window_end_us": 1_524_569_400_000_000,
        "onset_us": 1_524_567_950_000_000,
        "victim": "205.251.192.0/23 → AS16509 (AWS/Route 53)",
        "attacker": "AS10297 (eNet, an Ohio ISP)",
        "attacker_asn": 10297,
        "hijack_prefix": "205.251.192.0/24",
        "path_note": "/24 more-specific cut from inside Route 53's /23 supernet.",
    },
    "google_ntt_leak_2017": {
        "incident_type": "leak",
        "headline": "Google → Verizon → NTT OCN route leak",
        "when": "2017-08-25 · 03:22:54 UTC onset",
        "story": (
            "AS15169 (Google) accidentally leaked ~160k prefixes to AS701 (Verizon), "
            "which propagated them globally. The worst-hit downstream was AS4713 "
            "(NTT OCN) — large parts of Japan lost internet access for ~1 hour. "
            "Classic customer-cone violation."
        ),
        "fixture_rel": "data/google_leak_2017.duckdb",
        "baseline_rel": None,
        "asrel_rel": "data/caida_asrel_2017_08.duckdb",
        "window_start_us": 1_503_631_200_000_000,
        "window_end_us": 1_503_633_600_000_000,
        "onset_us": 1_503_631_377_000_000,
        "victim": "AS4713 (NTT OCN)",
        "attacker": "AS15169 (Google) via AS701 (Verizon)",
        "attacker_asn": 4713,
        "hijack_prefix": None,
        "path_note": (
            "Canonical leak path: AS3333 → AS1103 → AS286 → AS701 → AS15169 → AS4713. "
            "Standard valley-free leaks because CAIDA doesn't have the 15169-4713 "
            "pair; the cone-aware detector catches it."
        ),
    },
    "mainone_google_leak_2018": {
        "incident_type": "leak",
        "headline": "MainOne → China Telecom → Russia route leak",
        "when": "2018-11-12 · 21:12:16 UTC onset",
        "story": (
            "AS37282 (MainOne, Nigeria) accepted Google's prefixes from a peer and "
            "propagated them upstream to AS4809 (China Telecom) → AS20485 (Transtelecom) "
            "→ tier-1 AS2914 (NTT). Textbook Type-1 RFC 7908 leak; for ~74 minutes "
            "Google traffic transited through China and Russia."
        ),
        "fixture_rel": "data/mainone_2018.duckdb",
        "baseline_rel": None,
        "asrel_rel": "data/caida_asrel_2018_11.duckdb",
        "window_start_us": 1_542_057_136_000_000,
        "window_end_us": 1_542_061_536_000_000,
        "onset_us": 1_542_057_136_000_000,
        "victim": "AS15169 (Google)",
        "attacker": "AS37282 (MainOne)",
        "attacker_asn": 15169,
        "hijack_prefix": None,
        "path_note": (
            "Canonical leak path: AS15562 → AS2914 → AS20485 → AS4809 → AS37282 → AS15169. "
            "203 distinct Google prefixes observed leaking through MainOne in the 90-minute "
            "window. Detected via valley-free + customer-cone path inference."
        ),
    },
    "rostelecom_2017": {
        "incident_type": "hijack",
        "headline": "Rostelecom (AS12389) financial-network hijack",
        "when": "2017-04-26 · 22:36:39 UTC onset",
        "story": (
            "AS12389 briefly re-announced ~36 prefixes belonging to major US "
            "financial networks — including Mastercard, Visa, and several "
            "federal allocations — on 2017-04-26. The hijack reached RRC00 via "
            "AS1273 (Vodafone) on the canonical path '3333 1273 12389' and "
            "lasted about 10 minutes."
        ),
        "fixture_rel": "data/rostelecom_2017.duckdb",
        "baseline_rel": "data/baselines/rostelecom_2017_baseline.duckdb",
        "asrel_rel": None,
        "window_start_us": 1_493_245_800_000_000,
        "window_end_us": 1_493_247_600_000_000,
        "onset_us": 1_493_246_199_000_000,
        "victim": "AS26380 (Mastercard/Edgenet) · AS2559 (PSI/USPS) · others",
        "attacker": "AS12389 (Rostelecom)",
        "attacker_asn": 12389,
        "hijack_prefix": "216.119.216.0/24",
        "path_note": (
            "Canonical reach path '3333 → 1273 → 12389' put the hijack on RRC00 "
            "directly via Vodafone (AS1273)."
        ),
    },
    "vodafone_idea_2024": {
        "incident_type": "leak",
        "headline": "Vodafone Idea (AS55410) tier-1-to-tier-1 leak",
        "when": "2024-09-30 · 04:50:00 UTC onset",
        "story": (
            "AS55410 (Vodafone Idea / Vi India) propagated routes between its "
            "two upstream tier-1s — AS9498 (Bharti Airtel) and AS45528 (Tata "
            "Communications) — with a 6× AS55410 path-prepend. A botched "
            "traffic-engineering attempt turned into a Type-1 RFC 7908 leak; "
            "224 distinct prefixes propagated through Vi between two networks "
            "neither of which is its customer."
        ),
        "fixture_rel": "data/vodafone_2024.duckdb",
        "baseline_rel": None,
        "asrel_rel": "data/caida_asrel_2024_09.duckdb",
        "window_start_us": 1_727_671_800_000_000,
        "window_end_us": 1_727_673_600_000_000,
        "onset_us": 1_727_671_800_000_000,
        "victim": "AS45528 (Tata) and downstream",
        "attacker": "AS55410 (Vodafone Idea)",
        "attacker_asn": 55410,
        "hijack_prefix": None,
        "path_note": (
            "Canonical leak shape: AS9498 → AS55410 ×6 → AS45528 ×5. "
            "AS55410 is customer to both AS9498 and AS45528; propagating "
            "either direction is a valley-free violation."
        ),
    },
}


def _demo_render_panel(
    inc_id: str,
    headline: str,
    when: str,
    story: str,
    victim: str,
    attacker: str,
) -> None:
    """Show the narrative header before any detection runs."""
    from rich.padding import Padding
    from rich.panel import Panel

    title = f"[bold cyan]⚡ NetPulse[/] [dim]·[/] {inc_id}"
    body = (
        f"[bold white]{headline}[/]\n"
        f"[dim]{when}[/]\n\n"
        f"{story}\n\n"
        f"[dim]Victim:[/]   {victim}\n"
        f"[dim]Attacker:[/] {attacker}"
    )
    console.print(
        Padding(Panel(body, title=title, border_style="cyan", expand=False), (0, 0, 1, 0))
    )


def _demo_render_hijack_path(
    store_path: Path,
    attacker_asn: int,
    hijack_prefix: str | None,
    path_note: str,
) -> None:
    """Pull the canonical hijacker path from the BGP store and render it.

    Looks up the first observed path that originates at ``attacker_asn``
    (optionally constrained to ``hijack_prefix``) and renders it as an
    arrow-separated AS chain with the attacker AS highlighted.
    """
    import duckdb
    from rich.panel import Panel

    sql = "SELECT prefix, as_path, timestamp_us FROM bgp_records WHERE origin_as = ?"
    params: list[Any] = [attacker_asn]
    if hijack_prefix is not None:
        sql += " AND prefix = ?"
        params.append(hijack_prefix)
    sql += " ORDER BY timestamp_us LIMIT 1"

    try:
        con = duckdb.connect(str(store_path), read_only=True)
        row = con.execute(sql, params).fetchone()
    except Exception:
        return
    if row is None:
        return
    prefix, as_path, _ts = row
    if not as_path:
        return

    hops = str(as_path).split()
    rendered_hops: list[str] = []
    for hop in hops:
        try:
            asn = int(hop)
        except ValueError:
            rendered_hops.append(hop)
            continue
        name = _AS_NAMES.get(asn)
        # The path can have ~6 hops; printing "AS<n> (Name)" on every
        # one bloats the line. Render the attacker with its name
        # bold-red; the rest plain.
        if asn == attacker_asn:
            label = f"[bold red]AS{asn} ({name})[/]" if name else f"[bold red]AS{asn}[/]"
        else:
            label = f"AS{asn}"
        rendered_hops.append(label)
    path_str = " [dim]→[/] ".join(rendered_hops) + " [dim]←ORIGIN[/]"

    body = f"[bold]{prefix}[/] announced via:\n\n  {path_str}\n\n[dim]{path_note}[/]"
    console.print(
        Panel(
            body,
            title="[yellow]⚠ Hijacker path observed at RRC00[/]",
            border_style="yellow",
            expand=False,
        )
    )
    console.print()


def _demo_render_alerts(
    alerts: list[Any],
    show_all: bool,
    incident_prefix: str | None,
    max_rows: int = 8,
) -> int:
    """Render alerts as a colorized Rich Table grouped by severity.

    Returns the number of alerts actually displayed. Behavior:
    - ``show_all=False`` (default) drops MOAS warnings on prefixes
      unrelated to the labeled incident so the headline isn't drowned
      by noise.
    - After filtering, the table is truncated to ``max_rows`` and a
      single "+N more" footer row is added. ``--all`` shows everything.
    """
    from rich.table import Table

    severity_color = {"critical": "red", "warning": "yellow", "info": "cyan"}
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    sorted_alerts = sorted(alerts, key=lambda a: severity_order.get(a.severity, 3))

    if show_all or incident_prefix is None:
        kept = sorted_alerts
        filtered_out = 0
    else:
        # An alert is on-target if (a) it's critical (always the
        # headline) (b) it's a subprefix_hijack alert, or (c) its
        # prefix shares the first 16 bits with the incident's prefix.
        def _is_on_target(a: Any) -> bool:
            if a.severity == "critical":
                return True
            if a.detector == "subprefix_hijack":
                return True
            try:
                a_first16 = ".".join(a.entity.split(".")[:2])
                inc_first16 = ".".join(incident_prefix.split(".")[:2])
                return a_first16 == inc_first16
            except (AttributeError, IndexError):
                return False

        kept = [a for a in sorted_alerts if _is_on_target(a)]
        filtered_out = len(sorted_alerts) - len(kept)

    # Truncate to keep the table visually scannable even on a
    # thousand-alert leak window.
    if show_all:
        displayed = kept
        truncated = 0
    elif len(kept) > max_rows:
        displayed = kept[:max_rows]
        truncated = len(kept) - max_rows
    else:
        displayed = kept
        truncated = 0

    table = Table(
        title=None,
        show_header=True,
        header_style="bold",
        border_style="dim",
        row_styles=["", "dim"],
        expand=False,
    )
    table.add_column("severity", style="bold", width=9)
    table.add_column("detector", style="cyan", width=18)
    table.add_column("entity", style="white", width=22, overflow="fold")
    table.add_column("summary", style="white", overflow="fold")

    for a in displayed:
        sev = a.severity
        color = severity_color.get(sev, "white")
        # Trim summaries that are very long (the cone-leak ones print
        # the full AS path; clip to keep the row count visible).
        summary = a.summary if len(a.summary) <= 120 else a.summary[:117] + "…"
        table.add_row(
            f"[{color}]{sev}[/]",
            a.detector,
            a.entity,
            summary,
        )
    if truncated > 0:
        table.add_row(
            "[dim]…[/]",
            "[dim]…[/]",
            "[dim]…[/]",
            f"[dim]+{truncated} more matching alerts (use --all to see them)[/]",
        )
    if filtered_out > 0:
        table.add_row(
            "[dim]warning[/]",
            "[dim]moas[/]",
            "[dim](other prefixes)[/]",
            f"[dim]{filtered_out} MOAS warnings on unrelated prefixes -- pass --all to show[/]",
        )
    console.print(table)
    return len(kept)


def _run_one_demo(incident_id: str, show_all: bool, repo_root: Path) -> dict[str, Any]:
    """Render one full incident demo and return a summary dict.

    Returns: ``{incident_id, verdict, color, by_detector, crit, warn,
    wall_ms, latency_us, success}``. ``success=False`` on missing
    data; the caller decides whether that's fatal.
    """
    import time as _time

    from rich.panel import Panel

    from netpulse.detectors.baseline import BGPBaseline
    from netpulse.detectors.moas import MOASDetector
    from netpulse.detectors.subprefix import SubPrefixHijackDetector
    from netpulse.features.bgp import extract_bgp_features
    from netpulse.storage.duckdb_store import BGPStore

    meta = _DEMO_STORIES[incident_id]
    fixture = repo_root / meta["fixture_rel"]
    window_start_us = int(meta["window_start_us"])
    window_end_us = int(meta["window_end_us"])

    _demo_render_panel(
        inc_id=incident_id,
        headline=str(meta["headline"]),
        when=str(meta["when"]),
        story=str(meta["story"]),
        victim=str(meta["victim"]),
        attacker=str(meta["attacker"]),
    )

    if not fixture.exists():
        console.print(f"[red]Fixture missing at {fixture}.[/]")
        if incident_id != "youtube_2008":
            console.print(
                "[dim]Fetch the incident's BGP data via the recipe in "
                f"data/incidents/{incident_id}.json → notes, then re-run.[/]"
            )
        return {
            "incident_id": incident_id,
            "verdict": "missing",
            "color": "dim",
            "by_detector": {},
            "crit": 0,
            "warn": 0,
            "wall_ms": 0.0,
            "latency_us": None,
            "success": False,
        }

    incident_type = str(meta.get("incident_type", "hijack"))

    # ----- Loading -----
    t0 = _time.perf_counter()
    all_alerts: list[Any] = []
    by_detector: dict[str, int] = {}
    detectors_run = 0

    if incident_type == "hijack":
        # Baseline: hand-curated for YouTube; loaded from baseline_rel
        # for the others.
        baseline_rel = meta.get("baseline_rel")
        if incident_id == "youtube_2008":
            baseline = BGPBaseline.build({"208.65.152.0/22": {36561}})
        elif baseline_rel is not None:
            baseline_p = repo_root / baseline_rel
            if baseline_p.exists():
                with BGPStore(baseline_p) as bs:
                    baseline = BGPBaseline.from_store(bs)
            else:
                baseline = BGPBaseline.build({})
        else:
            baseline = BGPBaseline.build({})

        with BGPStore(fixture) as store:
            feats = extract_bgp_features(store, window_start_us, window_end_us)
        load_ms = (_time.perf_counter() - t0) * 1000

        console.print(
            f"  [green]+[/] loaded fixture        "
            f"[bold]{feats.announce_total}[/]A · "
            f"[bold]{feats.withdraw_total}[/]W · "
            f"[bold]{len(feats.origins_by_prefix)}[/] distinct prefixes "
            f"[dim]({load_ms:.1f}ms)[/]"
        )
        console.print(
            f"  [green]+[/] built baseline        [bold]{len(baseline.origins)}[/] supernet(s)"
        )

        t1 = _time.perf_counter()
        hijack_detectors = [MOASDetector(), SubPrefixHijackDetector(baseline)]
        for det in hijack_detectors:
            alerts = det.score(feats)
            by_detector[det.name] = len(alerts)
            all_alerts.extend(alerts)
        detectors_run = len(hijack_detectors)
        detect_ms = (_time.perf_counter() - t1) * 1000
    else:
        # ----- Leak path (route_leak + customer_cone_leak) -----
        from netpulse.detectors.customer_cone import CustomerConeMap
        from netpulse.detectors.customer_cone_leak import CustomerConeLeakDetector
        from netpulse.detectors.route_leak import (
            ASRelationshipMap,
            ObservedPath,
            RouteLeakDetector,
            parse_as_path,
        )
        from netpulse.storage.asrel_store import ASRelStore

        asrel_rel = meta.get("asrel_rel")
        if asrel_rel is None:
            console.print("[red]Leak incident missing asrel_rel; can't run leak detectors.[/]")
            raise typer.Exit(1)
        asrel_p = repo_root / asrel_rel
        if not asrel_p.exists():
            console.print(f"[red]AS-relationships file missing at {asrel_p}.[/]")
            console.print(
                "[dim]Run `netpulse ingest asrel --out "
                f"{asrel_rel}` to fetch the matching CAIDA snapshot.[/]"
            )
            raise typer.Exit(1)

        with BGPStore(fixture) as store:
            rows = store.query(
                "SELECT timestamp_us, prefix, peer_as, as_path FROM bgp_records "
                "WHERE update_type='A' AND as_path IS NOT NULL "
                "  AND timestamp_us >= ? AND timestamp_us < ?",
                [window_start_us, window_end_us],
            )
        with ASRelStore(asrel_p) as ars:
            rels = ASRelationshipMap.from_store(ars)
        paths = []
        for ts, p, peer, asp in rows:
            asns = parse_as_path(str(asp))
            if asns:
                paths.append(
                    ObservedPath(prefix=str(p), asns=asns, peer_as=int(peer), timestamp_us=int(ts))
                )
        load_ms = (_time.perf_counter() - t0) * 1000
        console.print(
            f"  [green]+[/] loaded fixture        "
            f"[bold]{len(rows)}[/] announces, "
            f"[bold]{len(paths)}[/] valid paths "
            f"[dim]({load_ms:.1f}ms)[/]"
        )
        console.print(
            f"  [green]+[/] loaded AS-rels       "
            f"[bold]{len(rels.pairs)}[/] AS-pairs (CAIDA serial-2)"
        )

        t1 = _time.perf_counter()
        valley_alerts = RouteLeakDetector(rels=rels).score_paths(paths)
        cones = CustomerConeMap.from_relationships(rels)
        cone_alerts = CustomerConeLeakDetector(cones=cones).score_paths(paths)
        by_detector["route_leak"] = len(valley_alerts)
        by_detector["customer_cone_leak"] = len(cone_alerts)
        # Use whichever fired (cone is the catch-all that fires on
        # cases standard valley-free can't see, like google_ntt_2017).
        all_alerts = valley_alerts if len(valley_alerts) >= len(cone_alerts) else cone_alerts
        detectors_run = 2
        detect_ms = (_time.perf_counter() - t1) * 1000

    crit = sum(1 for a in all_alerts if a.severity == "critical")
    warn = sum(1 for a in all_alerts if a.severity == "warning")
    info = sum(1 for a in all_alerts if a.severity == "info")
    console.print(
        f"  [green]+[/] ran {detectors_run} detectors        "
        f"[bold red]{crit}[/] critical · "
        f"[bold yellow]{warn}[/] warning · "
        f"[bold cyan]{info}[/] info "
        f"[dim]({detect_ms:.1f}ms)[/]"
    )
    console.print()

    # ----- Hijacker AS path callout (pulled from real BGP data) -----
    attacker_asn = meta.get("attacker_asn")
    hijack_prefix = meta.get("hijack_prefix")
    path_note = meta.get("path_note", "")
    if attacker_asn is not None:
        _demo_render_hijack_path(fixture, int(attacker_asn), hijack_prefix, path_note)

    # ----- Alert table -----
    if all_alerts:
        _demo_render_alerts(all_alerts, show_all=show_all, incident_prefix=hijack_prefix)
    else:
        console.print("[dim]No alerts in window.[/]")

    # ----- Stream-latency callout (hijack incidents only) -----
    # Replays the incident record-by-record through the sub-prefix
    # detector and reports the microsecond delta from documented
    # onset to first qualifying alert. Caches the result so the
    # caller can fold it into the summary table.
    stream_latency_us: int | None = None
    if (
        incident_type == "hijack"
        and "subprefix_hijack" in by_detector
        and by_detector["subprefix_hijack"] > 0
    ):
        try:
            from netpulse.benchmark.incident import Incident
            from netpulse.benchmark.streaming_replay import replay_subprefix_streaming

            inc_for_replay = Incident(
                id=incident_id,
                name=str(meta["headline"]),
                kind="hijack",
                start_us=window_start_us,
                end_us=window_end_us,
                expected_detectors=["subprefix_hijack"],
                source_url="",
                prefix=meta.get("hijack_prefix"),
                attacker_asn=meta.get("attacker_asn"),
                victim_asn=None,
                onset_us=int(meta.get("onset_us") or window_start_us),
            )
            with BGPStore(fixture) as store:
                sr = replay_subprefix_streaming(inc_for_replay, store, baseline)
            stream_latency_us = sr.latency_from_onset_us
        except Exception:
            stream_latency_us = None

    # ----- Verdict panel: color + emoji track outcome -----
    console.print()
    fired_detectors = [k for k, v in by_detector.items() if v > 0]
    detector_summary = ", ".join(f"{k}={v}" for k, v in by_detector.items() if v > 0)
    # For leak incidents the headline alert severity is "warning"
    # (leak detectors don't escalate to critical), so a leak that
    # fires gets a HIJACK/LEAK DETECTED verdict, not "Warnings only".
    leak_fired = incident_type == "leak" and any(v > 0 for v in by_detector.values())
    if crit > 0:
        verdict_color = "red"
        verdict_label = "[bold red]✗ HIJACK DETECTED[/]"
        verdict_text = "HIJACK"
    elif leak_fired:
        verdict_color = "red"
        verdict_label = "[bold red]✗ LEAK DETECTED[/]"
        verdict_text = "LEAK"
    elif warn > 0:
        verdict_color = "yellow"
        verdict_label = "[bold yellow]⚠ Warnings only[/]"
        verdict_text = "warnings"
    else:
        verdict_color = "green"
        verdict_label = "[bold green]✓ Clean window[/]"
        verdict_text = "clean"
    if not detector_summary:
        detector_summary = "[dim]nothing fired[/]"

    latency_str = ""
    if stream_latency_us is not None:
        if stream_latency_us <= 0:
            latency_str = "  [dim]·[/]  [bold green]0µs from onset[/]"
        elif stream_latency_us < 1_000_000:
            latency_str = f"  [dim]·[/]  [green]{stream_latency_us}µs from onset[/]"
        else:
            latency_str = f"  [dim]·[/]  {stream_latency_us / 1_000_000:.2f}s from onset"

    summary = (
        f"{verdict_label}  [dim]·[/]  {detector_summary}"
        + f"  [dim]·[/]  {len(fired_detectors)}/{detectors_run} detector(s)"
        + f"  [dim]·[/]  {(load_ms + detect_ms):.1f}ms wall"
        + latency_str
    )
    console.print(Panel(summary, border_style=verdict_color, expand=False))

    return {
        "incident_id": incident_id,
        "verdict": verdict_text,
        "color": verdict_color,
        "by_detector": dict(by_detector),
        "crit": crit,
        "warn": warn,
        "wall_ms": load_ms + detect_ms,
        "latency_us": stream_latency_us,
        "success": True,
    }


def _render_demo_summary_table(results: list[dict[str, Any]]) -> None:
    """After --incident all, render a per-incident roll-up table."""
    from rich.table import Table

    table = Table(
        title="[bold cyan]netpulse demo --incident all  ·  roll-up[/]",
        border_style="cyan",
        show_header=True,
        header_style="bold",
        expand=False,
    )
    table.add_column("incident id", style="bold cyan")
    table.add_column("verdict", style="bold")
    table.add_column("detector alerts", style="white", overflow="fold")
    table.add_column("wall", style="white", justify="right")
    table.add_column("latency", style="white", justify="right")

    verdict_paint = {
        "HIJACK": "[bold red]✗ HIJACK[/]",
        "LEAK": "[bold red]✗ LEAK[/]",
        "warnings": "[bold yellow]⚠ warn[/]",
        "clean": "[bold green]✓ clean[/]",
        "missing": "[dim]— missing[/]",
    }
    for r in results:
        alerts = ", ".join(f"{k}={v}" for k, v in r["by_detector"].items() if v > 0) or "[dim]—[/]"
        wall = f"{r['wall_ms']:.0f}ms" if r["wall_ms"] else "—"
        if r.get("latency_us") is None:
            latency = "[dim]—[/]"
        elif r["latency_us"] <= 0:
            latency = "[bold green]0µs[/]"
        elif r["latency_us"] < 1_000_000:
            latency = f"[green]{r['latency_us']}µs[/]"
        else:
            latency = f"{r['latency_us'] / 1_000_000:.2f}s"
        table.add_row(
            r["incident_id"],
            verdict_paint.get(r["verdict"], r["verdict"]),
            alerts,
            wall,
            latency,
        )
    console.print(table)


def _run_live_demo(seconds: int) -> None:
    """Tap RIS Live for ``seconds`` and stream BGP through MOAS in real time.

    Renders a live-updating Rich panel showing rolling counts of
    updates seen, prefixes touched, peers, and any alerts fired. At
    the end, prints a summary panel + a small "headline numbers"
    block so the demo viewer leaves with concrete figures.
    """
    import time as _time
    from collections import deque

    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table

    from netpulse.alerts.dedup import AlertDeduper
    from netpulse.detectors.moas import MOASDetector
    from netpulse.features.bgp import BGPWindowFeatures
    from netpulse.ingest.stream import StreamUpdate, stream_updates

    if seconds <= 0 or seconds > 600:
        console.print("[red]--live seconds must be 1..600.[/]")
        raise typer.Exit(1)

    # Story panel up front so the viewer knows what's about to happen.
    intro = (
        f"[bold white]Tapping RIPE RIS Live for {seconds}s[/]\n\n"
        f"Every BGP update on the public RIS WebSocket flows through "
        f"NetPulse's MOAS detector. The counters below update in real "
        f"time as peers from every RIS collector report announcements "
        f"and withdrawals."
    )
    console.print(
        Panel(
            intro,
            title="[bold cyan]⚡ NetPulse · live tap[/]",
            border_style="cyan",
            expand=False,
        )
    )
    console.print()

    moas = MOASDetector()
    deduper = AlertDeduper()
    rolling: deque[StreamUpdate] = deque()
    window_us = 60 * 1_000_000  # 60-second rolling window

    started = _time.monotonic()
    deadline = started + seconds
    total_updates = 0
    total_alerts = 0
    last_recompute = 0.0
    peers: set[int] = set()
    hosts: set[str] = set()

    def _panel(now: float, alerts_seen: int) -> Panel:
        elapsed = now - started
        remaining = max(0.0, deadline - now)
        rate = total_updates / max(elapsed, 0.001)
        body = (
            f"[bold green]{total_updates:>7,}[/] updates    "
            f"[dim]({rate:.0f}/s)[/]\n"
            f"[bold]{len(rolling):>7,}[/] in 60s window\n"
            f"[bold cyan]{len(peers):>7}[/] distinct peers\n"
            f"[bold cyan]{len(hosts):>7}[/] RIS collectors observed\n"
            f"[bold {'red' if alerts_seen else 'dim'}]{alerts_seen:>7}[/] MOAS alerts emitted\n\n"
            f"[dim]elapsed {elapsed:.0f}s · remaining {remaining:.0f}s[/]"
        )
        border = "red" if alerts_seen > 0 else "green"
        return Panel(body, title="[bold]live[/]", border_style=border, expand=False)

    try:
        with Live(_panel(_time.monotonic(), 0), refresh_per_second=4, console=console) as live:
            for upd in stream_updates():
                total_updates += 1
                rolling.append(upd)
                hosts.add(upd.host)
                peers.add(upd.peer_asn)

                now_wall = _time.monotonic()
                # Trim the rolling window to 60s of stream-time.
                cutoff = upd.timestamp_us - window_us
                while rolling and rolling[0].timestamp_us < cutoff:
                    rolling.popleft()

                # Recompute detector + repaint at most 4 times/sec.
                if now_wall - last_recompute >= 0.25:
                    last_recompute = now_wall
                    feats = BGPWindowFeatures(
                        window_start_us=cutoff,
                        window_end_us=upd.timestamp_us,
                    )
                    for r in rolling:
                        if r.update_type == "A":
                            feats.announce_count_by_prefix[r.prefix] = (
                                feats.announce_count_by_prefix.get(r.prefix, 0) + 1
                            )
                            if r.origin_as is not None:
                                feats.origins_by_prefix.setdefault(r.prefix, set()).add(r.origin_as)
                        else:
                            feats.withdraw_count_by_prefix[r.prefix] = (
                                feats.withdraw_count_by_prefix.get(r.prefix, 0) + 1
                            )
                    raw_alerts = moas.score(feats)
                    fresh = list(deduper.filter(raw_alerts))
                    total_alerts += len(fresh)
                    live.update(_panel(now_wall, total_alerts))

                if now_wall >= deadline:
                    break
    except KeyboardInterrupt:
        console.print("[dim]stopped by user[/]")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]live stream failed: {e}[/]")
        console.print(
            "[dim]This usually means the RIS Live WebSocket couldn't be reached. "
            "Try `uv run netpulse demo` (offline, bundled fixture) instead.[/]"
        )
        return

    # ----- Final summary -----
    elapsed = _time.monotonic() - started
    summary_table = Table(
        title="[bold cyan]live tap summary[/]",
        border_style="cyan",
        show_header=False,
        expand=False,
    )
    summary_table.add_column("k", style="dim")
    summary_table.add_column("v", style="bold")
    summary_table.add_row("Duration", f"{elapsed:.1f}s")
    summary_table.add_row("Updates received", f"{total_updates:,}")
    summary_table.add_row("Average rate", f"{total_updates / max(elapsed, 0.001):.0f} updates/s")
    summary_table.add_row("Distinct peers", str(len(peers)))
    summary_table.add_row("RIS collectors observed", str(len(hosts)))
    summary_table.add_row("MOAS alerts emitted", str(total_alerts))
    console.print()
    console.print(summary_table)
    console.print(
        "[dim]MOAS alerts on a live tap are mostly anycast / multi-homed prefixes "
        "(Google AS15169 / Cloudflare AS13335 / Akamai). The "
        "[/][cyan]netpulse stream --baseline path/to/rib.duckdb[/] "
        "[dim]flow adds sub-prefix detection on top.[/]"
    )


@app.command("demo")
def demo(
    incident_id: Annotated[
        str,
        typer.Option(
            "--incident",
            help=(
                "Incident id to replay, or 'all' to play every curated "
                "incident with a summary table."
            ),
        ),
    ] = "youtube_2008",
    show_list: Annotated[
        bool,
        typer.Option(
            "--list",
            help="List the curated incidents available to --incident, then exit.",
        ),
    ] = False,
    show_all: Annotated[
        bool,
        typer.Option(
            "--all",
            help=(
                "Show every alert. Default hides MOAS warnings on "
                "prefixes unrelated to the incident."
            ),
        ),
    ] = False,
    live_seconds: Annotated[
        int,
        typer.Option(
            "--live",
            help=(
                "Tap RIPE RIS Live for N seconds with live counters + "
                "MOAS detection, instead of replaying a labeled incident. "
                "Set to 0 to disable (default)."
            ),
        ),
    ] = 0,
) -> None:
    """Replay a labeled BGP incident against a bundled or local fixture (~1s, no setup).

    The default runs the canonical 2008 YouTube /24 sub-prefix hijack against
    a bundled real-data fixture. Use ``--incident <id>`` for any of the
    other curated corpus incidents, ``--incident all`` to play every one
    back-to-back with a final summary, ``--list`` to enumerate them,
    ``--all`` to include unrelated MOAS noise, and ``--live 30`` to
    swap the replay for a 30-second live tap of RIPE RIS Live.
    """
    from rich.table import Table

    repo_root = Path(__file__).resolve().parent.parent.parent

    # ----- --live short-circuit -----
    if live_seconds > 0:
        _run_live_demo(live_seconds)
        return

    # ----- --list short-circuit -----
    if show_list:
        list_table = Table(
            title="[bold cyan]netpulse demo --incident <id>[/]",
            border_style="cyan",
            show_header=True,
            header_style="bold",
            expand=False,
        )
        list_table.add_column("incident id", style="bold cyan")
        list_table.add_column("headline", style="white")
        list_table.add_column("when", style="dim")
        list_table.add_column("data?", style="white")
        for inc_id, meta in _DEMO_STORIES.items():
            fixture_path = repo_root / meta["fixture_rel"]
            data_status = "[green]bundled[/]" if fixture_path.exists() else "[yellow]fetch first[/]"
            list_table.add_row(inc_id, meta["headline"], meta["when"], data_status)
        console.print(list_table)
        return

    # ----- --incident all loop -----
    if incident_id == "all":
        results: list[dict[str, Any]] = []
        ids = list(_DEMO_STORIES.keys())
        for i, inc_id in enumerate(ids):
            results.append(_run_one_demo(inc_id, show_all, repo_root))
            if i < len(ids) - 1:
                console.print()
                console.rule(style="dim")
                console.print()
        console.print()
        _render_demo_summary_table(results)
        console.print(
            "[dim]Each row above is one labeled incident. "
            "Run `netpulse demo --incident <id>` to dive into a single case.[/]"
        )
        return

    if incident_id not in _DEMO_STORIES:
        console.print(
            f"[red]No demo for '{incident_id}'.[/] "
            f"Known incidents: {', '.join(sorted(_DEMO_STORIES))} (or 'all')"
        )
        raise typer.Exit(1)

    _run_one_demo(incident_id, show_all, repo_root)

    if incident_id == "youtube_2008":
        console.print(
            "[dim]Reproduce live: "
            "[/][cyan]curl -X POST https://netpulse-pauti.fly.dev/detect/bgp "
            "-H 'Content-Type: application/json' "
            '-d \'{"start_iso":"2008-02-24T18:45:00Z","duration_s":300}\'[/]'
        )
    console.print(
        "[dim]More:[/] [cyan]netpulse demo --incident all[/]"
        "  [dim]·[/]  [cyan]netpulse demo --list[/]"
        "  [dim]·[/]  [cyan]netpulse demo --all[/]"
    )


@app.command("serve")
def serve(
    store_path: Annotated[
        Path,
        typer.Option("--store", help="BGP DuckDB store the API will query."),
    ],
    baseline_path: Annotated[
        Path | None,
        typer.Option(
            "--baseline",
            help="Optional baseline DuckDB; enables sub-prefix detection.",
        ),
    ] = None,
    history_path: Annotated[
        Path | None,
        typer.Option(
            "--history",
            help="Optional alert-history DuckDB; enables GET /alerts queries.",
        ),
    ] = None,
    host: Annotated[str, typer.Option("--host", help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="TCP port.")] = 8000,
    log_format: Annotated[
        str,
        typer.Option(
            "--log-format",
            help="'json' (structured, default) or 'text' (human-readable).",
        ),
    ] = "json",
) -> None:
    """Serve BGP detectors as a FastAPI app (POST /detect/bgp, GET /health, GET /alerts)."""
    import uvicorn

    from netpulse.api.app import build_app
    from netpulse.observability import configure_logging

    if log_format not in ("json", "text"):
        raise typer.BadParameter("--log-format must be 'json' or 'text'")
    configure_logging(json_mode=(log_format == "json"))

    api = build_app(
        store_path=store_path,
        baseline_path=baseline_path,
        history_path=history_path,
    )
    console.log(
        f"serving NetPulse on http://{host}:{port} "
        f"(store={store_path}, baseline={baseline_path}, history={history_path})"
    )
    uvicorn.run(api, host=host, port=port)


@app.command("dashboard")
def dashboard(
    history_path: Annotated[
        Path,
        typer.Option(
            "--history",
            help=(
                "Alert-history DuckDB to visualize. Use the same path you "
                "passed to `netpulse stream --history` or "
                "`netpulse serve --history`."
            ),
        ),
    ],
    port: Annotated[int, typer.Option("--port", help="TCP port for Streamlit.")] = 8501,
    host: Annotated[str, typer.Option("--host", help="Bind address.")] = "127.0.0.1",
) -> None:
    """Launch the Streamlit alert-console dashboard over a NetPulse history DuckDB.

    Requires the optional 'dashboard' extra: `uv sync --extra dashboard`.
    """
    import shutil
    import subprocess
    import sys

    if not history_path.exists():
        raise typer.BadParameter(f"history file does not exist: {history_path}")

    streamlit_bin = shutil.which("streamlit")
    if streamlit_bin is None:
        console.log("[red]streamlit is not installed. Run `uv sync --extra dashboard` first.[/red]")
        raise typer.Exit(code=2)

    app_path = Path(__file__).parent / "dashboard" / "app.py"
    env = dict(**os.environ, NETPULSE_DASHBOARD_HISTORY=str(history_path.resolve()))
    console.log(f"launching Streamlit on http://{host}:{port} (history={history_path})")
    cmd = [
        streamlit_bin,
        "run",
        str(app_path),
        "--server.port",
        str(port),
        "--server.address",
        host,
        "--browser.gatherUsageStats",
        "false",
    ]
    # exec replaces this process so Ctrl-C lands cleanly in Streamlit.
    if sys.platform == "win32":
        # subprocess.call returns the exit code; Typer surfaces it.
        raise typer.Exit(code=subprocess.call(cmd, env=env))
    os.execve(streamlit_bin, cmd, env)


if __name__ == "__main__":
    app()
