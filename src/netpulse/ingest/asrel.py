"""Pull CAIDA's serial-2 inferred AS relationships into an ASRelStore.

Format (verified live 2026-05-10): bz2-compressed text, one
``as_a|as_b|rel|source`` line per inferred relationship. ``rel`` is ``-1``
for ``as_a`` is provider of ``as_b`` (p2c), ``0`` for peer-to-peer.
Comment lines start with ``#``.

The loader decompresses to a temp file and uses DuckDB's
``read_csv_auto`` + a CASE expression to insert in one statement, which
is roughly two orders of magnitude faster than per-row Python
``executemany`` over ~740k rows.
"""

from __future__ import annotations

import bz2
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

from netpulse.storage.asrel_schema import ASREL_TABLE
from netpulse.storage.asrel_store import ASRelStore


def latest_caida_url() -> str:
    """Default CAIDA URL for the first day of the current month."""
    today = date.today()
    fname = f"{today.year:04d}{today.month:02d}01.as-rel2.txt.bz2"
    return f"https://publicdata.caida.org/datasets/as-relationships/serial-2/{fname}"


def pull_caida_relationships(
    store: ASRelStore,
    source_url: str | None = None,
    timeout_s: int = 120,
) -> int:
    """Download the latest CAIDA serial-2 dump and load it into ``store``.

    Returns the number of relationship rows written.
    """
    url = source_url or latest_caida_url()

    with tempfile.NamedTemporaryFile(suffix=".bz2", delete=False) as tmp_bz:
        bz_path = Path(tmp_bz.name)
    txt_path = bz_path.with_suffix(".txt")

    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp, open(bz_path, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)

        with bz2.open(bz_path, "rb") as src, open(txt_path, "wb") as dst:
            for line in src:
                if line.startswith(b"#") or not line.strip():
                    continue
                dst.write(line)

        return _load_caida_csv_into_store(store, txt_path, source_label=_source_label(url))
    finally:
        bz_path.unlink(missing_ok=True)
        txt_path.unlink(missing_ok=True)


def _source_label(url: str) -> str:
    name = url.rsplit("/", 1)[-1]
    return f"caida-serial-2 {name}"


def _load_caida_csv_into_store(store: ASRelStore, txt_path: Path, source_label: str) -> int:
    insert_sql = f"""
    INSERT INTO {ASREL_TABLE} (as_a, as_b, relationship, source)
    SELECT
        CAST(column0 AS BIGINT) AS as_a,
        CAST(column1 AS BIGINT) AS as_b,
        CASE column2 WHEN '0' THEN 'p2p' WHEN '-1' THEN 'p2c' END AS relationship,
        ? AS source
    FROM read_csv_auto(
        ?,
        delim = '|',
        header = false,
        columns = {{
            'column0': 'VARCHAR',
            'column1': 'VARCHAR',
            'column2': 'VARCHAR',
            'column3': 'VARCHAR'
        }}
    )
    WHERE column2 IN ('0', '-1')
    """
    before = store.count()
    store.query(insert_sql, [source_label, str(txt_path)])
    return store.count() - before
