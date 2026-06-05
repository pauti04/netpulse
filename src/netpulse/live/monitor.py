"""The long-running monitor: tap RIS Live, detect, push to a DetectionFeed.

Hardened for 24/7 operation:
- Auto-reconnect with exponential backoff when the WebSocket drops.
- Bounded memory (a rolling time window; old updates are evicted).
- Per-(detector, entity) suppression so an ongoing anomaly is reported
  once per cooldown, not on every evaluation tick.
- Cooperative shutdown via a ``threading.Event``.

``run_monitor`` is blocking; the CLI runs it on a background thread while
the web server owns the main thread.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from netpulse.detectors.baseline import BGPBaseline
from netpulse.detectors.moas import MOASDetector
from netpulse.detectors.origin_deaggregation import OriginDeaggregationDetector
from netpulse.detectors.subprefix import SubPrefixHijackDetector
from netpulse.features.bgp import BGPWindowFeatures
from netpulse.ingest.stream import StreamUpdate, stream_updates
from netpulse.live.feed import Detection, DetectionFeed

_SUPPRESS_SECONDS = 300.0  # re-report an ongoing (detector, entity) at most every 5 min
_MAX_WINDOW = 200_000  # hard cap on buffered updates, to bound eval cost
_MOAS_MIN_ORIGINS = 3  # only surface multi-origin prefixes with 3+ origins (rarer, odder)


def _is_signal(alert: object) -> bool:
    """Filter the live feed to higher-signal events.

    The global table is full of *legitimate* 2-origin announcements
    (anycast, multi-homing), so plain MOAS would flood the feed. Surface
    MOAS only at 3+ origins; pass everything else (sub-prefix hijacks,
    deaggregation bursts) through.
    """
    detector = getattr(alert, "detector", "")
    if detector == "moas":
        origins = getattr(alert, "evidence", {}).get("origin_asns", [])
        return len(origins) >= _MOAS_MIN_ORIGINS
    return True


def _features_from_window(window: deque[StreamUpdate]) -> BGPWindowFeatures:
    """Aggregate a rolling deque of live updates into detector features."""
    if window:
        feats = BGPWindowFeatures(
            window_start_us=window[0].timestamp_us,
            window_end_us=window[-1].timestamp_us,
        )
    else:
        feats = BGPWindowFeatures(window_start_us=0, window_end_us=0)
    for upd in window:
        if upd.update_type == "A":
            feats.announce_count_by_prefix[upd.prefix] = (
                feats.announce_count_by_prefix.get(upd.prefix, 0) + 1
            )
            if upd.origin_as is not None:
                feats.origins_by_prefix.setdefault(upd.prefix, set()).add(upd.origin_as)
        else:
            feats.withdraw_count_by_prefix[upd.prefix] = (
                feats.withdraw_count_by_prefix.get(upd.prefix, 0) + 1
            )
    return feats


def run_monitor(
    feed: DetectionFeed,
    *,
    baseline: BGPBaseline | None = None,
    window_us: int = 60_000_000,
    interval_us: int = 10_000_000,
    host_filter: str | None = None,
    stop: threading.Event | None = None,
    max_backoff_s: float = 30.0,
) -> None:
    """Run the detect loop forever (until ``stop`` is set), reconnecting as needed."""
    detectors: list[object] = [MOASDetector(), OriginDeaggregationDetector()]
    if baseline is not None:
        detectors.append(SubPrefixHijackDetector(baseline))

    last_emit: dict[tuple[str, str], float] = {}
    backoff = 1.0

    interval_s = interval_us / 1_000_000
    while stop is None or not stop.is_set():
        window: deque[StreamUpdate] = deque(maxlen=_MAX_WINDOW)
        last_eval = time.monotonic()
        try:
            for upd in stream_updates(host_filter=host_filter):
                feed.set_connected(True)
                backoff = 1.0  # healthy connection resets backoff

                window.append(upd)
                feed.note_updates(1, upd.timestamp_us)

                # Wall-clock interval — robust to per-collector clock skew
                # in the RIS-Live timestamps, which is not monotonic.
                if time.monotonic() - last_eval >= interval_s:
                    last_eval = time.monotonic()
                    # Evict updates older than the time window before evaluating.
                    cutoff = upd.timestamp_us - window_us
                    while window and window[0].timestamp_us < cutoff:
                        window.popleft()
                    feed.note_window()
                    feats = _features_from_window(window)
                    now = time.monotonic()
                    fresh: list[Detection] = []
                    for det in detectors:
                        for a in det.score(feats):  # type: ignore[attr-defined]
                            if not _is_signal(a):
                                continue
                            key = (a.detector, a.entity)
                            if now - last_emit.get(key, 0.0) < _SUPPRESS_SECONDS:
                                continue
                            last_emit[key] = now
                            fresh.append(
                                Detection(
                                    ts_us=a.timestamp_us,
                                    detector=a.detector,
                                    severity=a.severity,
                                    entity=a.entity,
                                    summary=a.summary,
                                )
                            )
                    feed.add(fresh)

                if stop is not None and stop.is_set():
                    break
        except Exception:  # noqa: BLE001 — reconnect on any stream error
            feed.note_reconnect()
        finally:
            feed.set_connected(False)

        if stop is not None and stop.is_set():
            break
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff_s)
