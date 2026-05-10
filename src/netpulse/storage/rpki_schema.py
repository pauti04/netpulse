from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RPKIRecord:
    """One Validated ROA Payload (VRP).

    Mirrors the per-ROA shape published by Cloudflare / NTT / RIPE (rpki-client
    output, JSON form): an ``(asn, prefix, maxLength)`` tuple plus the trust
    anchor and expiry. ``expires_us`` is microseconds since the Unix epoch.
    """

    prefix: str
    asn: int
    max_length: int
    ta: str = ""
    expires_us: int = 0


RPKI_VRPS_TABLE = "rpki_vrps"


CREATE_RPKI_VRPS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {RPKI_VRPS_TABLE} (
    prefix     VARCHAR NOT NULL,
    asn        BIGINT NOT NULL,
    max_length INTEGER NOT NULL,
    ta         VARCHAR,
    expires_us BIGINT
);
"""

# Index intentionally not created during ingest -- the validator does one
# sequential scan to build its in-memory lookup, and per-batch index updates
# made bulk insert of 800k+ VRPs orders of magnitude slower in testing.


INSERT_RPKI_VRP = f"""
INSERT INTO {RPKI_VRPS_TABLE} (prefix, asn, max_length, ta, expires_us)
VALUES (?, ?, ?, ?, ?)
"""


def rpki_record_to_row(
    record: RPKIRecord,
) -> tuple[str, int, int, str, int]:
    return (record.prefix, record.asn, record.max_length, record.ta, record.expires_us)
