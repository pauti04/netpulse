from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AtlasPingRecord:
    """One probe-level ping measurement result.

    Mirrors the shape returned by ``ripe.atlas.cousteau.AtlasResultsRequest``
    for type=ping measurements. Timestamps are microseconds since the Unix
    epoch, UTC. ``avg_rtt_ms`` is ``None`` when all packets were lost.
    """

    timestamp_us: int
    msm_id: int
    prb_id: int
    dst_addr: str
    sent: int
    rcvd: int
    min_rtt_ms: float | None = None
    avg_rtt_ms: float | None = None
    max_rtt_ms: float | None = None


ATLAS_PING_TABLE = "atlas_ping"


CREATE_ATLAS_PING_TABLE = f"""
CREATE TABLE IF NOT EXISTS {ATLAS_PING_TABLE} (
    timestamp_us BIGINT NOT NULL,
    msm_id       BIGINT NOT NULL,
    prb_id       BIGINT NOT NULL,
    dst_addr     VARCHAR NOT NULL,
    sent         INTEGER NOT NULL,
    rcvd         INTEGER NOT NULL,
    min_rtt_ms   DOUBLE,
    avg_rtt_ms   DOUBLE,
    max_rtt_ms   DOUBLE
);
"""


INSERT_ATLAS_PING = f"""
INSERT INTO {ATLAS_PING_TABLE}
    (timestamp_us, msm_id, prb_id, dst_addr, sent, rcvd,
     min_rtt_ms, avg_rtt_ms, max_rtt_ms)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def atlas_ping_to_row(
    record: AtlasPingRecord,
) -> tuple[int, int, int, str, int, int, float | None, float | None, float | None]:
    return (
        record.timestamp_us,
        record.msm_id,
        record.prb_id,
        record.dst_addr,
        record.sent,
        record.rcvd,
        record.min_rtt_ms,
        record.avg_rtt_ms,
        record.max_rtt_ms,
    )
