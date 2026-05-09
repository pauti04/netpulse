"""BGP ingestion via pybgpstream (libBGPStream wrapper).

This module imports ``pybgpstream`` at load time and raises a descriptive
error if the native library is missing. That keeps callers from getting an
opaque ``ImportError`` deep inside their own code.

API surface used (pybgpstream >= 2.0):
- ``pybgpstream.BGPStream(from_time, until_time, collectors, record_type)``
- iterating the stream yields ``BGPElem`` objects with attributes:
  ``type`` (str: "A" announce / "W" withdraw / "R" rib),
  ``time`` (float epoch seconds), ``peer_asn`` (int), ``peer_address`` (str),
  ``collector`` (str), and ``fields`` (dict, with keys ``prefix``,
  ``as-path``, ``communities`` for announces; ``prefix`` for withdraws).
"""

from __future__ import annotations

try:
    import pybgpstream
except ImportError as e:  # pragma: no cover - import-time guard
    raise ImportError(
        "pybgpstream is required for BGP ingestion but failed to import. "
        "Install the native libBGPStream first "
        "(macOS: 'brew install libbgpstream'; Linux: see "
        "https://bgpstream.caida.org/docs/install) and then run 'uv sync'."
    ) from e

from netpulse.storage.duckdb_store import BGPStore
from netpulse.storage.schema import BGPRecord

_BATCH_SIZE = 5_000


def _parse_origin_as(as_path: str | None) -> int | None:
    """Return the right-most AS in the path, or None for AS-sets / missing paths."""
    if not as_path:
        return None
    last = as_path.split()[-1]
    if last.startswith("{"):
        # AS-set like "{64500,64600}" — origin is ambiguous, leave null.
        return None
    try:
        return int(last)
    except ValueError:
        return None


def _normalize_communities(value: object) -> str | None:
    """libBGPStream reports communities as a set/list of "asn:value" strings.

    Normalize to a single space-separated string for storage, or None if absent.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, (set, list, tuple)):
        items = sorted(str(c) for c in value)
        return " ".join(items) if items else None
    return str(value)


def pull_bgp_window(
    collector: str,
    start_us: int,
    end_us: int,
    store: BGPStore,
) -> int:
    """Pull BGP updates for ``[start_us, end_us)`` from ``collector`` into ``store``.

    Returns the number of records written.
    """
    if end_us <= start_us:
        raise ValueError("end_us must be greater than start_us")

    from_time = start_us // 1_000_000
    until_time = end_us // 1_000_000

    stream = pybgpstream.BGPStream(
        from_time=from_time,
        until_time=until_time,
        collectors=[collector],
        record_type="updates",
    )

    total = 0
    batch: list[BGPRecord] = []

    for elem in stream:
        update_type = getattr(elem, "type", None)
        if update_type not in ("A", "W"):
            continue

        fields = getattr(elem, "fields", {}) or {}
        prefix = fields.get("prefix")
        if not prefix:
            continue

        as_path = fields.get("as-path") if update_type == "A" else None
        communities = (
            _normalize_communities(fields.get("communities")) if update_type == "A" else None
        )

        batch.append(
            BGPRecord(
                timestamp_us=int(elem.time * 1_000_000),
                collector=str(elem.collector),
                peer_as=int(elem.peer_asn),
                peer_ip=str(elem.peer_address),
                prefix=str(prefix),
                update_type=update_type,
                origin_as=_parse_origin_as(as_path),
                as_path=as_path,
                communities=communities,
            )
        )

        if len(batch) >= _BATCH_SIZE:
            store.write_batch(batch)
            total += len(batch)
            batch.clear()

    if batch:
        store.write_batch(batch)
        total += len(batch)

    return total
