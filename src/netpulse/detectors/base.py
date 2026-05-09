"""Abstract base class for detectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

from netpulse.alerts import Alert

F = TypeVar("F")


class DetectorBase(ABC, Generic[F]):
    """Abstract base for detectors.

    Subclasses bind ``F`` to the feature-window type they consume (e.g.
    ``BGPWindowFeatures``) and implement ``score`` as a pure function over
    that window.
    """

    name: ClassVar[str] = ""

    @abstractmethod
    def score(self, features: F) -> list[Alert]:
        """Return zero or more alerts derived from a single feature window."""
