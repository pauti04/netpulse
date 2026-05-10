from __future__ import annotations

from dataclasses import dataclass

from netpulse.storage.atlas_schema import ATLAS_PING_TABLE
from netpulse.storage.atlas_store import AtlasPingStore


@dataclass(slots=True)
class AtlasPingWindowFeatures:
    """Aggregate ping features for one measurement over ``[start_us, end_us)``."""

    window_start_us: int
    window_end_us: int
    msm_id: int
    n_results: int
    n_full_loss: int  # rcvd == 0
    n_partial_loss: int  # 0 < rcvd < sent

    @property
    def full_loss_rate(self) -> float:
        return self.n_full_loss / self.n_results if self.n_results else 0.0

    @property
    def any_loss_rate(self) -> float:
        return (self.n_full_loss + self.n_partial_loss) / self.n_results if self.n_results else 0.0


def extract_atlas_features(
    store: AtlasPingStore,
    msm_id: int,
    start_us: int,
    end_us: int,
) -> AtlasPingWindowFeatures:
    if end_us <= start_us:
        raise ValueError("end_us must be greater than start_us")

    rows = store.query(
        f"""
        SELECT
            COUNT(*) AS n,
            SUM(CASE WHEN rcvd = 0 THEN 1 ELSE 0 END) AS full_loss,
            SUM(CASE WHEN rcvd > 0 AND rcvd < sent THEN 1 ELSE 0 END) AS partial_loss
        FROM {ATLAS_PING_TABLE}
        WHERE msm_id = ?
          AND timestamp_us >= ? AND timestamp_us < ?
        """,
        [msm_id, start_us, end_us],
    )
    n, full_loss, partial_loss = rows[0]
    return AtlasPingWindowFeatures(
        window_start_us=start_us,
        window_end_us=end_us,
        msm_id=msm_id,
        n_results=int(n or 0),
        n_full_loss=int(full_loss or 0),
        n_partial_loss=int(partial_loss or 0),
    )
