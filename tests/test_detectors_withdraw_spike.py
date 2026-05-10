from __future__ import annotations

from netpulse.detectors.withdraw_spike import WithdrawSpikeDetector
from netpulse.features.bgp import BGPWindowFeatures


def _features(silent: int, flapping: int = 0, healthy: int = 0) -> BGPWindowFeatures:
    """Build a synthetic window with explicit shapes:

    - silent: prefixes with withdrawals and no announces (the alert signal)
    - flapping: prefixes with both withdrawals AND announces (transient, ignored)
    - healthy: prefixes with announces only
    """
    feats = BGPWindowFeatures(window_start_us=0, window_end_us=60_000_000)
    n = 0
    for _ in range(silent):
        feats.withdraw_count_by_prefix[f"203.0.{n // 256}.{n % 256}/32"] = 1
        n += 1
    for _ in range(flapping):
        prefix = f"198.51.100.{n % 256}/32"
        feats.withdraw_count_by_prefix[prefix] = 1
        feats.origins_by_prefix[prefix] = {64600}
        feats.announce_count_by_prefix[prefix] = 1
        n += 1
    for _ in range(healthy):
        prefix = f"192.0.2.{n % 256}/32"
        feats.origins_by_prefix[prefix] = {64600}
        feats.announce_count_by_prefix[prefix] = 1
        n += 1
    return feats


def test_fires_when_many_prefixes_go_silent() -> None:
    feats = _features(silent=60, flapping=10, healthy=200)

    alerts = WithdrawSpikeDetector(min_silent_prefixes=50).score(feats)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.detector == "withdraw_spike"
    assert a.severity == "warning"
    assert a.evidence["n_silent_prefixes"] == 60


def test_silent_below_threshold_no_alert() -> None:
    feats = _features(silent=20)
    assert WithdrawSpikeDetector(min_silent_prefixes=50).score(feats) == []


def test_flapping_prefixes_do_not_count() -> None:
    # 100 flapping prefixes (W + A) should not trigger a 50-silent threshold
    # because they have a covering announce in the same window.
    feats = _features(silent=0, flapping=100)
    assert WithdrawSpikeDetector(min_silent_prefixes=50).score(feats) == []
