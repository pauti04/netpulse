from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

from netpulse.alerts import Alert

F = TypeVar("F")


class DetectorBase(ABC, Generic[F]):
    """Pure function from a feature window to zero or more alerts.

    Subclasses bind ``F`` to the feature type they consume (e.g.
    ``BGPWindowFeatures``).
    """

    name: ClassVar[str] = ""

    @abstractmethod
    def score(self, features: F) -> list[Alert]: ...
