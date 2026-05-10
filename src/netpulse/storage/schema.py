from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BGPRecord:
    """One BGP announce or withdraw, normalized.

    Timestamps are microseconds since the Unix epoch, UTC. ``update_type`` is
    "A" or "W". ``as_path`` and ``communities`` are space-separated.
    """

    timestamp_us: int
    collector: str
    peer_as: int
    peer_ip: str
    prefix: str
    update_type: str
    origin_as: int | None = None
    as_path: str | None = None
    communities: str | None = None


BGP_RECORDS_TABLE = "bgp_records"


CREATE_BGP_RECORDS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {BGP_RECORDS_TABLE} (
    timestamp_us BIGINT NOT NULL,
    collector    VARCHAR NOT NULL,
    peer_as      BIGINT NOT NULL,
    peer_ip      VARCHAR NOT NULL,
    prefix       VARCHAR NOT NULL,
    origin_as    BIGINT,
    as_path      VARCHAR,
    update_type  VARCHAR NOT NULL,
    communities  VARCHAR
);
"""


INSERT_BGP_RECORD = f"""
INSERT INTO {BGP_RECORDS_TABLE}
    (timestamp_us, collector, peer_as, peer_ip, prefix,
     origin_as, as_path, update_type, communities)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def record_to_row(
    record: BGPRecord,
) -> tuple[int, str, int, str, str, int | None, str | None, str, str | None]:
    return (
        record.timestamp_us,
        record.collector,
        record.peer_as,
        record.peer_ip,
        record.prefix,
        record.origin_as,
        record.as_path,
        record.update_type,
        record.communities,
    )
