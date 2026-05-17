"""FastAPI app exposing the BGP detectors over HTTP."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from netpulse import __version__
from netpulse.alerts import Alert
from netpulse.alerts.store import AlertHistoryStore
from netpulse.api.metrics import MetricsRegistry
from netpulse.detectors.base import DetectorBase
from netpulse.detectors.baseline import BGPBaseline
from netpulse.detectors.moas import MOASDetector
from netpulse.detectors.subprefix import SubPrefixHijackDetector
from netpulse.detectors.withdraw_spike import WithdrawSpikeDetector
from netpulse.features.bgp import BGPWindowFeatures, extract_bgp_features
from netpulse.storage.duckdb_store import BGPStore


class DetectRequest(BaseModel):
    """Window spec for a /detect/bgp call. The store and baseline are server-side."""

    start_iso: str = Field(..., description="ISO-8601, UTC if no offset.")
    duration_s: int = Field(..., gt=0, le=86400, description="Window length in seconds.")
    min_announce_count: int = Field(1, ge=1, description="MOAS threshold.")


class AlertOut(BaseModel):
    """JSON form of netpulse.alerts.Alert."""

    detector: str
    severity: Literal["info", "warning", "critical"]
    entity: str
    summary: str
    timestamp_us: int
    window_start_us: int
    window_end_us: int
    evidence: dict[str, Any]


class DetectResponse(BaseModel):
    window_start_us: int
    window_end_us: int
    announce_total: int
    withdraw_total: int
    distinct_prefixes: int
    alerts: list[AlertOut]


def _alert_to_out(a: Alert) -> AlertOut:
    return AlertOut(
        detector=a.detector,
        severity=a.severity,
        entity=a.entity,
        summary=a.summary,
        timestamp_us=a.timestamp_us,
        window_start_us=a.window_start_us,
        window_end_us=a.window_end_us,
        evidence=a.evidence,
    )


def _parse_iso_to_us(value: str) -> int:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000)


def build_app(
    store_path: Path,
    baseline_path: Path | None = None,
    history_path: Path | None = None,
) -> FastAPI:
    """Construct the FastAPI app bound to a fixed BGP store (and optional baseline)."""
    if not store_path.exists():
        raise FileNotFoundError(f"store {store_path} does not exist")
    if baseline_path is not None and not baseline_path.exists():
        raise FileNotFoundError(f"baseline {baseline_path} does not exist")

    api = FastAPI(
        title="NetPulse",
        version=__version__,
        description=(
            "BGP anomaly detectors over a configured DuckDB store. "
            "Store and baseline are configured at startup; clients only "
            "specify the time window."
        ),
    )

    baseline: BGPBaseline | None = None
    if baseline_path is not None:
        with BGPStore(baseline_path) as bs:
            baseline = BGPBaseline.from_store(bs)

    metrics = MetricsRegistry()
    requests_total = metrics.counter("netpulse_requests_total", "HTTP requests by endpoint.")
    alerts_total = metrics.counter(
        "netpulse_alerts_total", "Detector alerts emitted, labeled by detector."
    )
    baseline_prefixes_gauge = metrics.gauge(
        "netpulse_baseline_prefixes", "Sub-prefix baseline size at startup."
    )
    if baseline is not None:
        baseline_prefixes_gauge.set(float(len(baseline.origins)))

    @api.get("/health")
    def health() -> dict[str, str | int]:
        requests_total.inc(label_value="health")
        return {
            "status": "ok",
            "version": __version__,
            "store": str(store_path),
            "baseline_prefixes": len(baseline.origins) if baseline is not None else 0,
            "history": str(history_path) if history_path is not None else "",
        }

    @api.get("/metrics", response_class=PlainTextResponse)
    def metrics_endpoint() -> str:
        """Prometheus text-format metrics."""
        requests_total.inc(label_value="metrics")
        return metrics.render()

    @api.post("/detect/bgp", response_model=DetectResponse)
    def detect_bgp(req: DetectRequest) -> DetectResponse:
        requests_total.inc(label_value="detect_bgp")
        try:
            start_us = _parse_iso_to_us(req.start_iso)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        end_us = start_us + req.duration_s * 1_000_000

        store = BGPStore(store_path)
        try:
            features = extract_bgp_features(store, start_us, end_us)
        finally:
            store.close()

        detectors: list[DetectorBase[BGPWindowFeatures]] = [
            MOASDetector(min_announce_count=req.min_announce_count),
            WithdrawSpikeDetector(),
        ]
        if baseline is not None:
            detectors.append(SubPrefixHijackDetector(baseline))

        raw_alerts: list[Alert] = []
        for det in detectors:
            raw_alerts.extend(det.score(features))

        for a in raw_alerts:
            alerts_total.inc(label_value=a.detector)

        # Persist into the history store if one was configured at startup.
        if history_path is not None and raw_alerts:
            with AlertHistoryStore(history_path) as hist:
                hist.write_batch(raw_alerts)

        return DetectResponse(
            window_start_us=start_us,
            window_end_us=end_us,
            announce_total=features.announce_total,
            withdraw_total=features.withdraw_total,
            distinct_prefixes=len(features.origins_by_prefix),
            alerts=[_alert_to_out(a) for a in raw_alerts],
        )

    @api.get("/alerts", response_model=list[AlertOut])
    def list_alerts(
        since_iso: str = Query(..., description="ISO-8601 lower bound, inclusive."),
        until_iso: str = Query(..., description="ISO-8601 upper bound, exclusive."),
        detector: str | None = Query(None),
        severity: str | None = Query(None),
        limit: int = Query(1000, ge=1, le=10_000),
    ) -> list[AlertOut]:
        requests_total.inc(label_value="list_alerts")
        if history_path is None:
            raise HTTPException(
                status_code=404,
                detail="No alert history is configured for this server.",
            )
        try:
            since_us = _parse_iso_to_us(since_iso)
            until_us = _parse_iso_to_us(until_iso)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        with AlertHistoryStore(history_path) as hist:
            alerts = hist.query_window(
                since_us=since_us,
                until_us=until_us,
                detector=detector,
                severity=severity,
                limit=limit,
            )
        return [_alert_to_out(a) for a in alerts]

    return api
