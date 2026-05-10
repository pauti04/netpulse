from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict
from typing import Protocol

from rich.console import Console

from netpulse.alerts import Alert


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
