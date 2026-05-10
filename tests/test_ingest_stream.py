from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

from netpulse.ingest.stream import StreamUpdate, _parse_origin, stream_updates


def test_parse_origin_returns_none_for_empty_path() -> None:
    assert _parse_origin([]) is None
    assert _parse_origin(None) is None


def test_parse_origin_returns_last_int() -> None:
    assert _parse_origin([3333, 12859, 6461, 3491, 17557]) == 17557


def test_parse_origin_returns_none_for_as_set_at_origin() -> None:
    # libBGPStream / RIS Live render AS-sets as nested lists.
    assert _parse_origin([3333, 12859, [17557, 17558]]) is None


class _FakeWS:
    """A WebSocket stub that yields a fixed list of payloads, then EOFs."""

    def __init__(self, payloads: list[Any]) -> None:
        self._payloads = list(payloads)
        self.sent: list[str] = []

    def send(self, raw: str) -> None:
        self.sent.append(raw)

    def recv(self) -> str:
        if not self._payloads:
            return ""
        return json.dumps(self._payloads.pop(0))

    def close(self) -> None:
        pass


def _drain(it: Iterator[StreamUpdate]) -> list[StreamUpdate]:
    return list(it)


def test_stream_subscribes_and_yields_announces() -> None:
    fake = _FakeWS(
        [
            {
                "type": "ris_message",
                "data": {
                    "timestamp": 1_700_000_000.5,
                    "host": "rrc00.ripe.net",
                    "peer_asn": 64500,
                    "type": "UPDATE",
                    "path": [64500, 64600, 17557],
                    "announcements": [
                        {"next_hop": "1.2.3.4", "prefixes": ["192.0.2.0/24", "203.0.113.0/24"]}
                    ],
                    "withdrawals": [],
                },
            }
        ]
    )

    with patch("netpulse.ingest.stream.websocket.create_connection", return_value=fake):
        updates = _drain(stream_updates(client_id="test"))

    assert len(updates) == 2
    assert {u.prefix for u in updates} == {"192.0.2.0/24", "203.0.113.0/24"}
    for u in updates:
        assert u.timestamp_us == 1_700_000_000_500_000
        assert u.host == "rrc00.ripe.net"
        assert u.peer_asn == 64500
        assert u.update_type == "A"
        assert u.origin_as == 17557

    # Verify subscribe message looks right.
    assert len(fake.sent) == 1
    sub = json.loads(fake.sent[0])
    assert sub == {"type": "ris_subscribe", "data": {"type": "UPDATE"}}


def test_stream_yields_withdrawals_with_no_origin() -> None:
    fake = _FakeWS(
        [
            {
                "type": "ris_message",
                "data": {
                    "timestamp": 1_700_000_001.0,
                    "host": "rrc00.ripe.net",
                    "peer_asn": 64500,
                    "type": "UPDATE",
                    "path": [],
                    "announcements": [],
                    "withdrawals": ["192.0.2.0/24"],
                },
            }
        ]
    )
    with patch("netpulse.ingest.stream.websocket.create_connection", return_value=fake):
        updates = _drain(stream_updates())

    assert len(updates) == 1
    assert updates[0].update_type == "W"
    assert updates[0].origin_as is None


def test_stream_skips_non_ris_messages() -> None:
    fake = _FakeWS(
        [
            {"type": "ris_error", "data": {}},  # ignored
            {
                "type": "ris_message",
                "data": {
                    "timestamp": 1_700_000_002.0,
                    "host": "rrc00.ripe.net",
                    "peer_asn": 64500,
                    "type": "UPDATE",
                    "path": [64500, 17557],
                    "announcements": [{"next_hop": "1.2.3.4", "prefixes": ["192.0.2.0/24"]}],
                    "withdrawals": [],
                },
            },
        ]
    )
    with patch("netpulse.ingest.stream.websocket.create_connection", return_value=fake):
        updates = _drain(stream_updates())
    assert len(updates) == 1


def test_stream_passes_host_filter_in_subscribe() -> None:
    fake = _FakeWS([])
    with patch("netpulse.ingest.stream.websocket.create_connection", return_value=fake):
        _drain(stream_updates(host_filter="rrc03.ripe.net"))
    sub = json.loads(fake.sent[0])
    assert sub["data"]["host"] == "rrc03.ripe.net"
