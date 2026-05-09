from __future__ import annotations

import io

from rich.console import Console

from netpulse.alerts import Alert
from netpulse.alerts.publishers import StdoutPublisher


def _alert(**overrides: object) -> Alert:
    base: dict[str, object] = {
        "timestamp_us": 1_700_000_000_000_000,
        "detector": "moas",
        "severity": "warning",
        "entity": "192.0.2.0/24",
        "summary": "test alert",
        "window_start_us": 1_700_000_000_000_000,
        "window_end_us": 1_700_000_300_000_000,
    }
    base.update(overrides)
    return Alert(**base)  # type: ignore[arg-type]


def test_alert_defaults_evidence_to_empty_dict() -> None:
    a = _alert()
    assert a.evidence == {}


def test_stdout_publisher_writes_one_line_per_alert() -> None:
    buf = io.StringIO()
    pub = StdoutPublisher(console=Console(file=buf, force_terminal=False, width=200))

    written = pub.publish_all([_alert(), _alert(entity="203.0.113.0/24")])

    output = buf.getvalue()
    assert written == 2
    assert output.count("\n") == 2
    assert "192.0.2.0/24" in output
    assert "203.0.113.0/24" in output
    assert "moas" in output
