"""FastAPI app exposing the BGP detectors over HTTP."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from netpulse import __version__
from netpulse.alerts import Alert
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


def build_app(store_path: Path, baseline_path: Path | None = None) -> FastAPI:
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

    @api.get("/health")
    def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "version": __version__,
            "store": str(store_path),
            "baseline_prefixes": len(baseline.origins) if baseline is not None else 0,
        }

    @api.post("/detect/bgp", response_model=DetectResponse)
    def detect_bgp(req: DetectRequest) -> DetectResponse:
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

        alerts: list[AlertOut] = []
        for det in detectors:
            for a in det.score(features):
                alerts.append(_alert_to_out(a))

        return DetectResponse(
            window_start_us=start_us,
            window_end_us=end_us,
            announce_total=features.announce_total,
            withdraw_total=features.withdraw_total,
            distinct_prefixes=len(features.origins_by_prefix),
            alerts=alerts,
        )

    return api
