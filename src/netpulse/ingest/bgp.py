"""BGP ingestion via pybgpstream."""

from __future__ import annotations

try:
    import pybgpstream
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "pybgpstream failed to import. Install libBGPStream first "
        "(macOS: 'brew install bgpstream'; Linux: "
        "https://bgpstream.caida.org/docs/install), then re-run 'uv sync'."
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
    record_type: str = "updates",
    filter_str: str | None = None,
) -> int:
    """Pull ``[start_us, end_us)`` from ``collector`` into ``store``.

    ``record_type`` is ``"updates"`` (announces+withdraws) or ``"ribs"`` (a
    full table snapshot at each dump time within the window). RIB entries
    are stored with ``update_type='A'`` since semantically they are
    "currently announced".

    ``filter_str`` is the libBGPStream filter language (passed through to
    ``parse_filter_string``). Common forms: ``"prefix any 1.1.1.0/24"``
    matches exact, more-specific, or less-specific announcements of the
    given prefix; ``"peer-asn 12345"`` filters by peer; ``"path '_AS$'"``
    filters by AS-path regex. Pre-filtering inside libBGPStream is many
    times faster than post-filtering in Python; using
    ``filter_str="prefix any <supernet>"`` reduced one full ingest from
    several minutes to under 30 seconds during testing.
    """
    if end_us <= start_us:
        raise ValueError("end_us must be greater than start_us")

    stream_kwargs: dict[str, object] = {
        "from_time": start_us // 1_000_000,
        "until_time": end_us // 1_000_000,
        "collectors": [collector],
        "record_type": record_type,
    }
    if filter_str is not None:
        stream_kwargs["filter"] = filter_str
    stream = pybgpstream.BGPStream(**stream_kwargs)

    total = 0
    batch: list[BGPRecord] = []

    for elem in stream:
        update_type = getattr(elem, "type", None)
        if update_type == "R":
            update_type = "A"
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
