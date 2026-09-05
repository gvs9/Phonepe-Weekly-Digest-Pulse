"""
themes/clusterer.py
--------------------
Keyword-based review clusterer for Phase 2 — Thematic Grouping.

Public API
----------
    assign_themes(reviews, theme_config) -> List[Theme]
        Assigns every review to the first keyword-matching theme
        (priority = config order).  Reviews with no match go into a
        catch-all ``"other"`` Theme.

    rank_themes(themes) -> List[Theme]
        Returns only the named themes (excludes ``"other"``), sorted
        descending by review count.
"""

from __future__ import annotations

import logging
from typing import List

from ingestion import Review
from themes import OTHER, Theme, ThemeConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assign_themes(reviews: List[Review], theme_config: ThemeConfig) -> List[Theme]:
    """
    Assign each review to exactly one theme.

    Assignment rules
    ----------------
    * For each review, ``review.searchable_text()`` (lowercased title + text)
      is scanned for each keyword of each theme **in config order**.
    * The review is assigned to the **first** theme whose keyword list
      contains at least one match (substring match, case-insensitive).
    * Reviews that match no theme are assigned to the ``"other"`` bucket.
    * After assignment, a warning is logged for any named theme that
      received zero reviews.

    Parameters
    ----------
    reviews : List[Review]
        Normalised, noise-filtered reviews.
    theme_config : ThemeConfig
        Loaded theme definitions (from ``config.yaml``).

    Returns
    -------
    List[Theme]
        The themed Theme objects with ``.reviews`` populated.
        The ``"other"`` bucket is always the **last** element.

    Raises
    ------
    ValueError
        If ``reviews`` is empty.
    """
    if not reviews:
        raise ValueError("assign_themes: review list must not be empty.")

    # Reset review lists (safe to call multiple times)
    for theme in theme_config:
        theme.reviews = []

    other = Theme(name=OTHER, keywords=[], action_template="")

    matched = 0
    for review in reviews:
        searchable = review.searchable_text()   # lowercased title + text
        assigned = False
        for theme in theme_config:
            if _matches_any(searchable, theme.keywords):
                theme.reviews.append(review)
                review.theme = theme.name
                assigned = True
                matched += 1
                break
        if not assigned:
            other.reviews.append(review)
            review.theme = OTHER

    # Warn on zero-match named themes
    for theme in theme_config:
        if theme.count == 0:
            logger.warning(
                "Theme '%s' matched 0 reviews. Consider broadening its keywords.", theme.name
            )

    named = list(theme_config.themes)
    result = named + [other]

    logger.info(
        "assign_themes: %d reviews → %d matched, %d unmatched (other).",
        len(reviews), matched, other.count,
    )
    return result


def rank_themes(themes: List[Theme]) -> List[Theme]:
    """
    Return named themes (excluding ``"other"``), sorted descending by count.

    Parameters
    ----------
    themes : List[Theme]
        Output of :func:`assign_themes`.

    Returns
    -------
    List[Theme]
        Named themes sorted by ``count`` descending.  The ``"other"``
        bucket is excluded.
    """
    named = [t for t in themes if t.name != OTHER]
    return sorted(named, key=lambda t: t.count, reverse=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _matches_any(text: str, keywords: List[str]) -> bool:
    """
    Return True if *text* contains at least one keyword as a substring.

    Both *text* and all keywords are already lowercased by the caller.
    """
    return any(kw in text for kw in keywords)
