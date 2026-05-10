"""Pull a snapshot of validated ROAs into an RPKIStore.

The default source is Cloudflare's published rpki-client output. The shape
was verified against a live fetch (2026-05-10): top-level
``{"metadata": {...}, "roas": [{"asn": int, "prefix": str, "maxLength":
int, "ta": str, "expires": int}]}``.

Bulk loads use DuckDB's native ``read_json_auto`` + ``UNNEST`` pipeline
which is roughly two orders of magnitude faster than per-row Python
``executemany`` for the ~860k-row VRP set.
"""

from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path

from netpulse.storage.rpki_schema import RPKI_VRPS_TABLE
from netpulse.storage.rpki_store import RPKIStore

DEFAULT_SOURCE = "https://rpki.cloudflare.com/rpki.json"


def pull_rpki_snapshot(
    store: RPKIStore,
    source_url: str = DEFAULT_SOURCE,
    timeout_s: int = 300,
) -> int:
    """Download the ROA set and load it into ``store``. Returns row count written."""
    # Stream the JSON to a temp file rather than holding the whole 90+ MB
    # body in memory; DuckDB then ingests it in one SQL statement.
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(source_url, timeout=timeout_s) as resp:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    tmp.write(chunk)
            tmp.flush()
            tmp.close()
            return _load_rpki_json_into_store(store, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)


def _load_rpki_json_into_store(store: RPKIStore, json_path: Path) -> int:
    """DuckDB-native bulk load: read_json_auto + UNNEST + INSERT ... SELECT."""
    insert_sql = f"""
    INSERT INTO {RPKI_VRPS_TABLE} (prefix, asn, max_length, ta, expires_us)
    SELECT
        roa.prefix,
        CAST(roa.asn AS BIGINT)        AS asn,
        CAST(roa."maxLength" AS INTEGER) AS max_length,
        COALESCE(roa.ta, '')           AS ta,
        COALESCE(CAST(roa.expires AS BIGINT), 0) * 1000000 AS expires_us
    FROM (
        SELECT UNNEST(roas) AS roa
        FROM read_json_auto(?, maximum_object_size=536870912)
    )
    WHERE roa.prefix IS NOT NULL
      AND roa.asn IS NOT NULL
      AND roa."maxLength" IS NOT NULL
    """
    before = store.count()
    store.query(insert_sql, [str(json_path)])
    return store.count() - before
