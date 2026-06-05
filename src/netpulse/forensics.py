"""Forensic reconstruction of how a BGP anomaly propagated.

The ``demo`` command is a *snapshot*: "these detectors fired on this
window." This module answers the operator's next question — **how did it
spread?** How many independent vantage points (RIS / RouteViews peers)
observed the bad announcement, how fast it reached them, and how many
distinct AS paths carried it.

It works on the same `BGPStore` the detectors read, so it runs over any
incident in the corpus. The heavy lifting is three SQL aggregates plus a
pure assembler (`build_timeline`) that is trivially unit-testable.

Two match modes:

* **origin** — a prefix hijack: count peers that saw ``prefix`` originated
  by ``subject_asn``. The clean case (YouTube, MyEtherWallet, Rostelecom).
* **transit** — a route leak: count peers whose AS path *traversed*
  ``subject_asn`` (the leaking AS sits mid-path). Used when no single
  hijacked prefix identifies the event (MainOne, Vodafone Idea).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

MatchMode = Literal["origin", "transit"]


def _as_int(value: object) -> int:
    """Narrow a DuckDB cell (typed ``object``) to int. COUNT/MIN yield ints."""
    assert isinstance(value, int)
    return value


class _Queryable(Protocol):
    """Minimal read interface satisfied by ``BGPStore`` / ``MultiStoreBGPView``."""

    def query(self, sql: str, params: list[object] | None = ...) -> list[tuple[object, ...]]: ...


@dataclass(slots=True)
class PeerObservation:
    """One vantage point's first sighting of the anomalous announcement."""

    peer_as: int
    first_seen_us: int
    offset_from_onset_us: int


@dataclass(slots=True)
class PropagationTimeline:
    """How an anomaly spread across observable vantage points over time."""

    subject_asn: int
    prefix: str | None
    mode: MatchMode
    onset_us: int
    window_start_us: int
    window_end_us: int
    total_peers_in_window: int
    peers_reached: list[PeerObservation]  # sorted ascending by first_seen_us
    distinct_paths: int

    @property
    def reached_count(self) -> int:
        return len(self.peers_reached)

    @property
    def spread_pct(self) -> float:
        """Share of observable peers that saw the anomaly (0–100)."""
        if self.total_peers_in_window <= 0:
            return 0.0
        return 100.0 * self.reached_count / self.total_peers_in_window

    @property
    def time_to_first_us(self) -> int | None:
        """Offset from onset to the earliest observation (≥0), or None."""
        if not self.peers_reached:
            return None
        return max(0, self.peers_reached[0].offset_from_onset_us)

    @property
    def time_to_full_us(self) -> int | None:
        """Offset from onset to the last new vantage point reached, or None."""
        if not self.peers_reached:
            return None
        return max(0, self.peers_reached[-1].offset_from_onset_us)

    def spread_curve(self, n_buckets: int = 20) -> list[tuple[int, int]]:
        """Cumulative peers-reached sampled across ``n_buckets``.

        Returns ``[(offset_us_from_onset, cumulative_peers)]`` from the
        first observation to the last. Empty if nothing was reached.
        """
        if not self.peers_reached or n_buckets < 1:
            return []
        offsets = [max(0, p.offset_from_onset_us) for p in self.peers_reached]
        lo, hi = offsets[0], offsets[-1]
        if hi == lo:
            # Instantaneous: a single bucket holding everything.
            return [(lo, len(offsets))]
        step = (hi - lo) / n_buckets
        curve: list[tuple[int, int]] = []
        for i in range(1, n_buckets + 1):
            edge = lo + step * i
            cum = sum(1 for o in offsets if o <= edge)
            curve.append((int(edge), cum))
        return curve


def build_timeline(
    *,
    subject_asn: int,
    prefix: str | None,
    mode: MatchMode,
    onset_us: int,
    window_start_us: int,
    window_end_us: int,
    total_peers_in_window: int,
    peer_first_seen_us: dict[int, int],
    distinct_paths: int,
) -> PropagationTimeline:
    """Pure assembler — no I/O. ``peer_first_seen_us`` maps peer_as → earliest us."""
    observations = [
        PeerObservation(
            peer_as=peer_as,
            first_seen_us=first_us,
            offset_from_onset_us=first_us - onset_us,
        )
        for peer_as, first_us in peer_first_seen_us.items()
    ]
    observations.sort(key=lambda o: (o.first_seen_us, o.peer_as))
    return PropagationTimeline(
        subject_asn=subject_asn,
        prefix=prefix,
        mode=mode,
        onset_us=onset_us,
        window_start_us=window_start_us,
        window_end_us=window_end_us,
        total_peers_in_window=total_peers_in_window,
        peers_reached=observations,
        distinct_paths=distinct_paths,
    )


def reconstruct_propagation(
    store: _Queryable,
    *,
    subject_asn: int,
    prefix: str | None,
    onset_us: int,
    window_start_us: int,
    window_end_us: int,
    mode: MatchMode | None = None,
) -> PropagationTimeline:
    """Reconstruct the propagation timeline for ``subject_asn`` from a store.

    ``mode`` defaults to ``origin`` when a ``prefix`` is given, else
    ``transit``. Runs three aggregates: total observable peers in the
    window, per-peer first sighting of the anomaly, and the count of
    distinct AS paths that carried it.
    """
    resolved_mode: MatchMode = mode or ("origin" if prefix is not None else "transit")

    # The match predicate differs by mode. origin: prefix announced by the
    # subject AS. transit: the subject AS appears as a (non-origin) hop, so
    # match an interior " <asn> " token in the space-joined path.
    if resolved_mode == "origin":
        match_sql = "origin_as = ?"
        match_params: list[object] = [subject_asn]
        if prefix is not None:
            match_sql += " AND prefix = ?"
            match_params.append(prefix)
    else:
        # space-delimited contains; pad the path so boundary ASNs match too.
        match_sql = "(' ' || as_path || ' ') LIKE ?"
        match_params = [f"% {subject_asn} %"]

    window: list[object] = [window_start_us, window_end_us]

    total_peers = _as_int(
        store.query(
            "SELECT COUNT(DISTINCT peer_as) FROM bgp_records "
            "WHERE timestamp_us >= ? AND timestamp_us < ?",
            window,
        )[0][0]
    )

    first_seen_rows = store.query(
        "SELECT peer_as, MIN(timestamp_us) FROM bgp_records "
        f"WHERE timestamp_us >= ? AND timestamp_us < ? AND {match_sql} "
        "GROUP BY peer_as",
        window + match_params,
    )
    peer_first_seen_us = {_as_int(pa): _as_int(ts) for pa, ts in first_seen_rows}

    distinct_paths = _as_int(
        store.query(
            "SELECT COUNT(DISTINCT as_path) FROM bgp_records "
            f"WHERE timestamp_us >= ? AND timestamp_us < ? AND {match_sql}",
            window + match_params,
        )[0][0]
    )

    return build_timeline(
        subject_asn=subject_asn,
        prefix=prefix,
        mode=resolved_mode,
        onset_us=onset_us,
        window_start_us=window_start_us,
        window_end_us=window_end_us,
        total_peers_in_window=total_peers,
        peer_first_seen_us=peer_first_seen_us,
        distinct_paths=distinct_paths,
    )
