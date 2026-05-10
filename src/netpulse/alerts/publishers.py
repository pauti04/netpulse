from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict
from typing import Protocol

from rich.console import Console

from netpulse.alerts import Alert
from netpulse.alerts.store import AlertHistoryStore


class Publisher(Protocol):
    def publish(self, alert: Alert) -> None: ...
    def publish_all(self, alerts: Iterable[Alert]) -> int: ...


class StdoutPublisher:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def publish(self, alert: Alert) -> None:
        line = (
            f"[{alert.severity}] {alert.detector} :: {alert.entity} :: "
            f"{alert.summary} "
            f"(ts={alert.timestamp_us}, "
            f"window={alert.window_start_us}-{alert.window_end_us})"
        )
        # markup=False keeps "[warning]" from being eaten as a Rich style tag.
        self.console.print(line, markup=False, highlight=False)

    def publish_all(self, alerts: Iterable[Alert]) -> int:
        count = 0
        for a in alerts:
            self.publish(a)
            count += 1
        return count


class WebhookPublisher:
    """POST each alert as JSON to a configured URL.

    Designed for thin operator integrations (Slack incoming webhook, a
    PagerDuty Events API endpoint behind a relay, an internal alert bus).
    Failures are logged via ``on_error`` and do not raise -- a transient
    webhook outage should not crash the detector loop.
    """

    def __init__(
        self,
        url: str,
        timeout_s: float = 5.0,
        on_error: Console | None = None,
    ) -> None:
        self.url = url
        self.timeout_s = timeout_s
        self.on_error = on_error

    def publish(self, alert: Alert) -> None:
        body = json.dumps(asdict(alert)).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s):
                pass
        except (urllib.error.URLError, TimeoutError) as e:
            if self.on_error is not None:
                self.on_error.log(f"webhook publish failed for {alert.detector}: {e}")

    def publish_all(self, alerts: Iterable[Alert]) -> int:
        count = 0
        for a in alerts:
            self.publish(a)
            count += 1
        return count


class HistoryRecorder:
    """Persists every published alert to an AlertHistoryStore.

    Wraps another publisher so the recorder can sit alongside stdout or
    webhook delivery -- the original publisher still runs, the recorder
    just additionally writes the alert to the store.
    """

    def __init__(self, store: AlertHistoryStore, downstream: Publisher) -> None:
        self.store = store
        self.downstream = downstream

    def publish(self, alert: Alert) -> None:
        self.store.write(alert)
        self.downstream.publish(alert)

    def publish_all(self, alerts: Iterable[Alert]) -> int:
        # Materialize so the deduper / generator is consumed once.
        materialized = list(alerts)
        self.store.write_batch(materialized)
        return self.downstream.publish_all(materialized)
