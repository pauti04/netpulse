"""RIS Live WebSocket streaming.

API surface used (verified against ris-live.ripe.net on 2026-05-09):
- WebSocket endpoint: ``wss://ris-live.ripe.net/v1/ws/?client=...``.
- Send ``{"type": "ris_subscribe", "data": {<filters>}}`` to start
  receiving updates.
- Each incoming message is JSON ``{"type": "ris_message", "data": {...}}``
  with fields ``timestamp`` (float epoch seconds), ``peer``, ``peer_asn``,
  ``host`` (e.g. ``rrc03.ripe.net``), ``type`` (``"UPDATE"``), ``path``
  (list of ints; AS-sets nested as lists), ``announcements`` (list of
  ``{"next_hop": str, "prefixes": list[str]}``) and ``withdrawals``
  (list of prefix strings).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

try:
    import websocket
except ImportError as e:  # pragma: no cover
    raise ImportError("websocket-client is required for the stream subcommand.") from e


@dataclass(slots=True)
class StreamUpdate:
    """One normalized BGP update from RIS Live."""

    timestamp_us: int
    host: str
    peer_asn: int
    update_type: str  # "A" or "W"
    prefix: str
    origin_as: int | None  # None for withdrawals or AS-sets


def _parse_origin(path: list[Any] | None) -> int | None:
    if not path:
        return None
    last = path[-1]
    if isinstance(last, list):  # AS-set
        return None
    try:
        return int(last)
    except (TypeError, ValueError):
        return None


def stream_updates(
    client_id: str = "netpulse-stream",
    host_filter: str | None = None,
) -> Iterator[StreamUpdate]:
    """Yield StreamUpdate records from RIS Live until the connection drops or is closed."""
    sub_data: dict[str, Any] = {"type": "UPDATE"}
    if host_filter is not None:
        sub_data["host"] = host_filter

    ws = websocket.create_connection(f"wss://ris-live.ripe.net/v1/ws/?client={client_id}")
    try:
        ws.send(json.dumps({"type": "ris_subscribe", "data": sub_data}))
        while True:
            raw = ws.recv()
            if not raw:
                break
            msg = json.loads(raw)
            if msg.get("type") != "ris_message":
                continue
            d = msg.get("data", {})
            ts = d.get("timestamp")
            if ts is None:
                continue
            ts_us = int(float(ts) * 1_000_000)
            host = str(d.get("host", ""))
            peer_asn_raw = d.get("peer_asn")
            try:
                peer_asn = int(peer_asn_raw) if peer_asn_raw is not None else 0
            except (TypeError, ValueError):
                peer_asn = 0

            origin_as = _parse_origin(d.get("path"))

            for prefix in d.get("withdrawals") or []:
                yield StreamUpdate(
                    timestamp_us=ts_us,
                    host=host,
                    peer_asn=peer_asn,
                    update_type="W",
                    prefix=str(prefix),
                    origin_as=None,
                )

            for ann in d.get("announcements") or []:
                for prefix in ann.get("prefixes", []):
                    yield StreamUpdate(
                        timestamp_us=ts_us,
                        host=host,
                        peer_asn=peer_asn,
                        update_type="A",
                        prefix=str(prefix),
                        origin_as=origin_as,
                    )
    finally:
        ws.close()
