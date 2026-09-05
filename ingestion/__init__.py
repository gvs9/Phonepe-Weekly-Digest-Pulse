"""
ingestion/__init__.py
---------------------
Review dataclass and shared exceptions for the ingestion layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class InsufficientDataError(Exception):
    """Raised when there are not enough reviews to build a pulse."""


class SchemaError(Exception):
    """Raised when a review export file is missing required columns."""


class ConfigError(Exception):
    """Raised when config.yaml is missing required keys or has invalid values."""


# ---------------------------------------------------------------------------
# Source type
# ---------------------------------------------------------------------------

Source = Literal["app_store", "play_store", "unknown"]

# ---------------------------------------------------------------------------
# Review dataclass
# ---------------------------------------------------------------------------

@dataclass
class Review:
    """
    Canonical, normalised representation of a single store review.

    All dates are stored as UTC-aware datetimes.
    """

    id: str
    source: Source
    rating: int          # 1–5
    title: str           # may be empty string
    text: str            # full review body, never empty
    date: datetime       # UTC-aware

    # Assigned by Phase 2; not set during ingestion
    theme: str = field(default="", repr=False)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not self.text.strip():
            raise ValueError(f"Review '{self.id}': text must not be empty.")
        if not (1 <= self.rating <= 5):
            raise ValueError(
                f"Review '{self.id}': rating must be 1–5, got {self.rating!r}."
            )
        if not isinstance(self.date, datetime):
            raise TypeError(
                f"Review '{self.id}': date must be a datetime, got {type(self.date)}."
            )
        # Ensure the datetime is always timezone-aware (UTC)
        if self.date.tzinfo is None:
            raise ValueError(
                f"Review '{self.id}': date must be timezone-aware (UTC)."
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def stars(self) -> str:
        """Return a star-rating string like ★★★☆☆."""
        return "★" * self.rating + "☆" * (5 - self.rating)

    def searchable_text(self) -> str:
        """Return lowercased combined title + text for keyword matching."""
        return f"{self.title} {self.text}".lower()

    def __str__(self) -> str:  # pragma: no cover
        date_str = self.date.strftime("%Y-%m-%d")
        return (
            f"[{self.source}] {self.stars} ({date_str}): "
            f"{self.text[:80]}{'...' if len(self.text) > 80 else ''}"
        )
