# Adding a new detector

The fastest way to extend NetPulse is to add a detector. A detector
is a small, pure function over a feature window — input is a typed
window object, output is zero or more `Alert` records. The existing
detectors (`moas.py`, `subprefix.py`, `withdraw_spike.py`,
`atlas_loss.py`, `rpki.py`, `route_leak.py`) are all under 150 lines.

This walkthrough adds a hypothetical `LongPathDetector` that flags
prefixes whose AS path length is unusually large — a heuristic for
"my route is taking a strange detour."

## 1. Pick a feature shape

Detectors are generic over the feature type they consume:

```python
class DetectorBase(ABC, Generic[F]):
    name: ClassVar[str] = ""

    @abstractmethod
    def score(self, features: F) -> list[Alert]: ...
```

Existing feature types:

| Feature                           | Source                                       |
| --------------------------------- | -------------------------------------------- |
| `BGPWindowFeatures`               | `features.bgp.extract_bgp_features` over a BGP store |
| `AtlasPingWindowFeatures`         | `features.atlas.extract_atlas_features` over an Atlas store |
| `ObservedPath` (one-shot, not aggregated) | `RouteLeakDetector` works on raw paths       |

If your detector needs paths (not just per-prefix origins), you'll add
a per-path-iterating detector like `RouteLeakDetector`. Otherwise
`BGPWindowFeatures` is the standard input — and you'll likely need to
extend it with whatever new aggregate your detector consumes.

For `LongPathDetector` we need the AS-path *length* per observed
record, which `BGPWindowFeatures` does not currently track. We'd
extend the feature extractor:

```python
# src/netpulse/features/bgp.py
@dataclass(slots=True)
class BGPWindowFeatures:
    ...
    max_path_len_by_prefix: dict[str, int] = field(default_factory=dict)

def extract_bgp_features(...):
    ...
    rows = store.query("""
        SELECT prefix, origin_as, update_type, COUNT(*),
               MAX(LENGTH(as_path) - LENGTH(REPLACE(as_path, ' ', ''))) + 1 AS max_len
        FROM bgp_records WHERE timestamp_us >= ? AND timestamp_us < ?
        GROUP BY prefix, origin_as, update_type
    """, [start_us, end_us])
```

(Above is illustrative; the existing extractor doesn't track path
length, but the schema is extensible.)

## 2. Implement the detector

```python
# src/netpulse/detectors/long_path.py
from dataclasses import dataclass
from typing import ClassVar

from netpulse.alerts import Alert
from netpulse.detectors.base import DetectorBase
from netpulse.features.bgp import BGPWindowFeatures


@dataclass
class LongPathDetector(DetectorBase[BGPWindowFeatures]):
    name: ClassVar[str] = "long_path"
    threshold: int = 10  # alert if path is this long or longer

    def score(self, features: BGPWindowFeatures) -> list[Alert]:
        alerts = []
        for prefix, max_len in features.max_path_len_by_prefix.items():
            if max_len < self.threshold:
                continue
            alerts.append(Alert(
                timestamp_us=features.window_end_us,
                detector=self.name,
                severity="warning",
                entity=prefix,
                summary=f"AS-path length {max_len} >= threshold {self.threshold}",
                window_start_us=features.window_start_us,
                window_end_us=features.window_end_us,
                evidence={"max_path_len": max_len, "threshold": self.threshold},
            ))
        return alerts
```

## 3. Test it

Synthetic feature input, asserted alert output:

```python
# tests/test_detectors_long_path.py
from netpulse.detectors.long_path import LongPathDetector
from netpulse.features.bgp import BGPWindowFeatures


def test_fires_above_threshold() -> None:
    feats = BGPWindowFeatures(
        window_start_us=0, window_end_us=1_000_000,
        max_path_len_by_prefix={"203.0.113.0/24": 12},
    )
    alerts = LongPathDetector(threshold=10).score(feats)
    assert len(alerts) == 1
    assert alerts[0].evidence["max_path_len"] == 12


def test_silent_below_threshold() -> None:
    feats = BGPWindowFeatures(
        window_start_us=0, window_end_us=1_000_000,
        max_path_len_by_prefix={"203.0.113.0/24": 5},
    )
    assert LongPathDetector(threshold=10).score(feats) == []
```

`make test` should pass.

## 4. Wire into the CLI

Add an entry to `detect bgp` in `src/netpulse/cli.py`:

```python
from netpulse.detectors.long_path import LongPathDetector
detectors.append(LongPathDetector(threshold=long_path_threshold))
```

Or expose a separate `detect long-path` subcommand if the detector
takes its own configuration.

## 5. Update the architecture diagram

If you want the detector visible on the README's mermaid flowchart,
add it to the list of `Features --> X` rows.

## 6. (Optional) Add a labeled incident the detector should catch

If your detector targets a specific shape — say, a particular leak
from operator history — add a labeled incident that the detector is
expected to fire on. See `data/incidents/_README.md` for the schema
and citation rules.

## What the review will look at

- Test coverage of the detector's positive AND negative cases.
- A short docstring explaining what signal the detector watches and
  what it intentionally does *not* try to detect.
- An honest false-positive estimate: ideally a real-archive run on a
  background hour where the detector should *not* fire, with the alert
  count.
- Mypy strict + ruff clean.
- No new top-level dependencies without flagging in the PR.
