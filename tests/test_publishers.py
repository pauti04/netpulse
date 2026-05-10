from __future__ import annotations

import json
from unittest.mock import patch

from netpulse.alerts import Alert
from netpulse.alerts.publishers import WebhookPublisher


def _alert() -> Alert:
    return Alert(
        timestamp_us=1_700_000_000_000_000,
        detector="moas",
        severity="warning",
        entity="192.0.2.0/24",
        summary="x",
        window_start_us=0,
        window_end_us=1_700_000_000_000_000,
    )


class _FakeResp:
    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_webhook_publisher_posts_json() -> None:
    seen: list[tuple[str, bytes, str]] = []

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        seen.append((req.full_url, req.data, req.get_header("Content-type")))
        return _FakeResp()

    with patch("netpulse.alerts.publishers.urllib.request.urlopen", side_effect=fake_urlopen):
        WebhookPublisher("https://example.test/hook").publish(_alert())

    assert len(seen) == 1
    url, body, content_type = seen[0]
    assert url == "https://example.test/hook"
    assert content_type == "application/json"
    payload = json.loads(body)
    assert payload["detector"] == "moas"
    assert payload["entity"] == "192.0.2.0/24"


def test_webhook_publisher_swallows_errors() -> None:
    import urllib.error

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        raise urllib.error.URLError("nope")

    # Should not raise -- a transient webhook outage shouldn't crash the loop.
    with patch("netpulse.alerts.publishers.urllib.request.urlopen", side_effect=fake_urlopen):
        WebhookPublisher("https://example.test/hook").publish_all([_alert(), _alert()])
