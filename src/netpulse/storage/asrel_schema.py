"""Schema for CAIDA-style AS relationship records.

CAIDA's serial-2 inferred relationships have one row per ordered pair:
``<as0>|<as1>|<rel>`` where ``rel`` is ``-1`` (as0 is provider of as1),
``0`` (peer-to-peer), or sometimes ``1`` for sibling. NetPulse stores
both directions for symmetric peer relations and the canonical direction
for provider→customer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Relationship = Literal["p2c", "c2p", "p2p", "sibling"]


@dataclass(slots=True)
class ASRelationship:
    """One inferred relationship between an ordered pair of ASes."""

    as_a: int
    as_b: int
    relationship: Relationship
    source: str = ""


ASREL_TABLE = "as_relationships"


CREATE_ASREL_TABLE = f"""
CREATE TABLE IF NOT EXISTS {ASREL_TABLE} (
    as_a         BIGINT NOT NULL,
    as_b         BIGINT NOT NULL,
    relationship VARCHAR NOT NULL,
    source       VARCHAR
);
"""


INSERT_ASREL = f"""
INSERT INTO {ASREL_TABLE} (as_a, as_b, relationship, source) VALUES (?, ?, ?, ?)
"""


def asrel_to_row(record: ASRelationship) -> tuple[int, int, str, str]:
    return (record.as_a, record.as_b, record.relationship, record.source)
