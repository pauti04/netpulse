from __future__ import annotations

from collections.abc import Iterable

from rich.console import Console

from netpulse.alerts import Alert


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
