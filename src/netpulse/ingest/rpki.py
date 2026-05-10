"""Pull a snapshot of validated ROAs into an RPKIStore.

The default source is Cloudflare's published rpki-client output. The shape
was verified against a live fetch (2026-05-10): top-level
``{"metadata": {...}, "roas": [{"asn": int, "prefix": str, "maxLength":
int, "ta": str, "expires": int}]}``.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from netpulse.storage.rpki_schema import RPKIRecord
from netpulse.storage.rpki_store import RPKIStore

DEFAULT_SOURCE = "https://rpki.cloudflare.com/rpki.json"
_BATCH_SIZE = 5_000


def _record_from_roa(roa: dict[str, Any]) -> RPKIRecord | None:
    try:
        prefix = str(roa["prefix"])
        asn = int(roa["asn"])
        max_length = int(roa["maxLength"])
    except (KeyError, ValueError, TypeError):
        return None
    expires = roa.get("expires") or 0
    try:
        expires_us = int(expires) * 1_000_000
    except (ValueError, TypeError):
        expires_us = 0
    return RPKIRecord(
        prefix=prefix,
        asn=asn,
        max_length=max_length,
        ta=str(roa.get("ta", "")),
        expires_us=expires_us,
    )


def pull_rpki_snapshot(
    store: RPKIStore,
    source_url: str = DEFAULT_SOURCE,
    timeout_s: int = 120,
) -> int:
    """Download the ROA set and load it into ``store``. Returns row count written."""
    with urllib.request.urlopen(source_url, timeout=timeout_s) as resp:
        payload = json.load(resp)

    roas = payload.get("roas", [])
    if not isinstance(roas, list):
        raise ValueError("expected 'roas' to be a list in the source JSON")

    batch: list[RPKIRecord] = []
    total = 0
    for roa in roas:
        if not isinstance(roa, dict):
            continue
        record = _record_from_roa(roa)
        if record is None:
            continue
        batch.append(record)
        if len(batch) >= _BATCH_SIZE:
            total += store.write_batch(batch)
            batch.clear()
    if batch:
        total += store.write_batch(batch)
    return total
