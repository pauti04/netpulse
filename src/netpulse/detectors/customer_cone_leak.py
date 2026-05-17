"""Customer-cone-aware route-leak detector.

Strictly more sensitive than the valley-free check in
:mod:`netpulse.detectors.route_leak`: walks each observed AS-path
left-to-right, classifies every adjacent step as *downhill* (the next
AS is in the current AS's transitive customer cone) or *uphill*
(it isn't), and flags any path containing a downhill step followed
later by an uphill step.

Why this is sharper than bilateral valley-free:

- The valley-free check at the pair level abstains when CAIDA doesn't
  infer the specific adjacent pair (returns ``unknown`` and folds it
  into "could be valid"). Cones are *transitive* and so survive sparse
  inference on individual pairs as long as the broader cone shape is
  known.
- The 2017-08-25 Google → Verizon → NTT OCN leak is the worked example
  this detector exists to catch. The canonical leak path
  ``3333 1103 286 701 15169 4713`` has pair-direction sequence
  ``[c2p, c2p, c2p, p2c, unknown]`` against the 2017-08 CAIDA snapshot,
  so the valley-free check abstains. Customer cones make the leak
  visible: 4713 (NTT OCN) is not in cone(15169) (Google's customer
  cone has 10 ASes in 2017-08); the step 15169→4713 is "uphill", and
  it follows the "downhill" step 701→15169, so the path has a valley.

Unknown adjacencies do not produce false positives: a step is
"downhill" only when there is *positive evidence* (the child AS is in
the parent's transitive cone). Missing data leaves the step "uphill",
which is fine on its own; the alert requires the down-then-up sequence.

Operates on raw paths (same shape as the valley-free detector) rather
than the prefix-aggregated window features because path inspection is
what the algorithm needs.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from netpulse.alerts import Alert
from netpulse.detectors.customer_cone import CustomerConeMap
from netpulse.detectors.route_leak import ObservedPath

StepShape = Literal["downhill", "uphill"]


def classify_path(path: Sequence[int], cones: CustomerConeMap) -> tuple[bool, list[StepShape]]:
    """Return ``(is_leak, per-step shapes)`` using customer-cone direction.

    A step ``a -> b`` is *downhill* if ``b`` is in the transitive
    customer cone of ``a``, *uphill* otherwise. A leak is any path
    containing a downhill step followed (any number of steps later) by
    an uphill step.
    """
    shapes: list[StepShape] = []
    for i in range(len(path) - 1):
        a, b = int(path[i]), int(path[i + 1])
        shapes.append("downhill" if cones.contains(a, b) else "uphill")

    saw_downhill = False
    for s in shapes:
        if s == "downhill":
            saw_downhill = True
        elif s == "uphill" and saw_downhill:
            return True, shapes
    return False, shapes


@dataclass
class CustomerConeLeakDetector:
    """Flag observed BGP paths whose direction is not customer-cone-monotone."""

    name: ClassVar[str] = "customer_cone_leak"
    cones: CustomerConeMap

    def score_paths(self, paths: Iterable[ObservedPath]) -> list[Alert]:
        alerts: list[Alert] = []
        for p in paths:
            leak, shapes = classify_path(p.asns, self.cones)
            if not leak:
                continue
            alerts.append(
                Alert(
                    timestamp_us=p.timestamp_us,
                    detector=self.name,
                    severity="warning",
                    entity=p.prefix,
                    summary=(
                        f"path {p.asns} for {p.prefix} contains a customer-cone valley "
                        f"(shapes: {shapes})"
                    ),
                    window_start_us=p.timestamp_us,
                    window_end_us=p.timestamp_us,
                    evidence={
                        "path": p.asns,
                        "step_shapes": shapes,
                        "peer_as": p.peer_as,
                    },
                )
            )
        return alerts
