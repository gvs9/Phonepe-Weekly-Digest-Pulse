"""
themes/__init__.py
------------------
Theme dataclass and config loader for Phase 2 — Thematic Grouping.

A Theme holds:
    name         : str            — human-readable theme label (e.g. "payments")
    keywords     : List[str]      — case-insensitive match terms from config.yaml
    action_template : str         — canned action idea for the pulse (Phase 3)
    reviews      : List[Review]   — reviews assigned to this theme (populated by clusterer)

ThemeConfig wraps the list of Theme objects loaded from config.yaml and
validates that at most 5 named themes are defined.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from ingestion import ConfigError, Review

logger = logging.getLogger(__name__)

# Maximum named themes allowed by the spec
MAX_THEMES = 5

# Sentinel name for the catch-all bucket
OTHER = "other"


@dataclass
class Theme:
    """
    A single configurable theme.

    Attributes
    ----------
    name : str
        Theme identifier, e.g. ``"payments"``.  Use ``"other"`` for the
        unmatched catch-all bucket.
    keywords : List[str]
        Keyword / phrase list.  Matching is case-insensitive substring search
        on ``review.searchable_text()``.
    action_template : str
        Rule-based action idea used by the Pulse Generator (Phase 3).
    reviews : List[Review]
        Reviews assigned to this theme by the clusterer.  Populated in-place
        by :func:`themes.clusterer.assign_themes`.
    """

    name: str
    keywords: List[str] = field(default_factory=list)
    action_template: str = ""
    reviews: List[Review] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of reviews assigned to this theme."""
        return len(self.reviews)

    def __str__(self) -> str:  # pragma: no cover
        label = f"[{self.name}]" if self.name == OTHER else self.name
        return f"{label:<15} {self.count:>4} reviews"


class ThemeConfig:
    """
    Loads and validates the theme definitions from ``config.yaml``.

    Parameters
    ----------
    raw_themes : list[dict]
        The ``themes`` list from the parsed YAML config dict.

    Raises
    ------
    ConfigError
        If more than ``MAX_THEMES`` (5) named themes are defined, or if the
        ``themes`` key is missing / not a list.
    """

    def __init__(self, raw_themes: list[dict]) -> None:
        if not isinstance(raw_themes, list):
            raise ConfigError(
                "config.yaml: 'themes' must be a list of theme definitions."
            )
        if len(raw_themes) > MAX_THEMES:
            raise ConfigError(
                f"config.yaml defines {len(raw_themes)} themes; "
                f"maximum allowed is {MAX_THEMES}. "
                "Remove extra themes or merge them."
            )

        self.themes: List[Theme] = []
        for entry in raw_themes:
            name = str(entry.get("name", "")).strip().lower()
            if not name:
                raise ConfigError(
                    "config.yaml: every theme entry must have a non-empty 'name'."
                )
            keywords = [str(k).strip().lower() for k in entry.get("keywords", []) if str(k).strip()]
            action = str(entry.get("action_template", "")).strip()
            self.themes.append(Theme(name=name, keywords=keywords, action_template=action))

        logger.info("ThemeConfig: loaded %d themes: %s", len(self.themes), [t.name for t in self.themes])

    def __iter__(self):
        return iter(self.themes)

    def __len__(self):
        return len(self.themes)

    @classmethod
    def from_config(cls, config: dict) -> "ThemeConfig":
        """
        Convenience factory — accepts the top-level config dict from
        ``config.yaml`` and extracts the ``themes`` list automatically.

        Raises
        ------
        ConfigError
            If the ``themes`` key is absent.
        """
        raw = config.get("themes")
        if raw is None:
            raise ConfigError(
                "config.yaml is missing the required 'themes' key. "
                "Add at least one theme definition."
            )
        return cls(raw)
