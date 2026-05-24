"""NetPulse CLI entry point."""

from __future__ import annotations

import os
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
    if baseline_path is not None:
        with BGPStore(baseline_path) as bs:
            baseline = BGPBaseline.from_store(bs)
        console.log(f"loaded baseline: {len(baseline.origins)} prefixes")
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


@app.command("demo")
def demo() -> None:
    """Run the YouTube/Pakistan 2008 hijack against a bundled fixture (~1s, no setup)."""
    from netpulse.alerts.publishers import StdoutPublisher
    from netpulse.detectors.baseline import BGPBaseline
    from netpulse.detectors.moas import MOASDetector
    from netpulse.detectors.subprefix import SubPrefixHijackDetector
    from netpulse.features.bgp import extract_bgp_features
    from netpulse.storage.duckdb_store import BGPStore

    repo_root = Path(__file__).resolve().parent.parent.parent
    fixture = repo_root / "data" / "fixtures" / "youtube_2008_demo.duckdb"
    if not fixture.exists():
        console.print(f"[red]Demo fixture missing at {fixture}.[/]")
        console.print(
            "Run from a clone of the repo, or regenerate via scripts/extract_demo_fixture.py."
        )
        raise typer.Exit(1)

    # 2008-02-24 18:45:00 UTC -- 18:50:00 UTC; 18:47:57 UTC is the documented onset.
    window_start_us = 1_203_878_700_000_000
    window_end_us = 1_203_879_000_000_000
    onset_us = 1_203_878_877_000_000

    baseline = BGPBaseline.build({"208.65.152.0/22": {36561}})

    with BGPStore(fixture) as store:
        feats = extract_bgp_features(store, window_start_us, window_end_us)

    console.print("[bold]NetPulse demo[/] — 5-minute RRC00 slice around the YouTube hijack.")
    console.print(
        f"  records:    {feats.announce_total} announces / {feats.withdraw_total} withdraws"
    )
    console.print(f"  prefixes:   {len(feats.origins_by_prefix)} distinct")
    console.print("  baseline:   1 supernet ([cyan]208.65.152.0/22 -> AS36561[/])")
    console.print("  onset:      2008-02-24 18:47:57 UTC (AS17557 announces 208.65.153.0/24)")
    console.print()

    detectors = [MOASDetector(), SubPrefixHijackDetector(baseline)]
    publisher = StdoutPublisher(console=console)
    by_detector: dict[str, int] = {}
    for det in detectors:
        alerts = det.score(feats)
        by_detector[det.name] = len(alerts)
        publisher.publish_all(alerts)

    console.print()
    console.print(
        "[bold green]Result[/]: "
        + ", ".join(f"{n}={k}" for n, k in by_detector.items())
        + f" -- onset at us={onset_us}, window_end us={window_end_us}"
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
