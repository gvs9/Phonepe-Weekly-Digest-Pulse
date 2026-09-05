"""
pulse/generator.py
------------------
Phase 3 — Pulse Generator

Selects quotes, generates action ideas, and mines emerging issues.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import List, Optional

from ingestion import Review
from pulse import PulseNote
from themes import OTHER, Theme

logger = logging.getLogger(__name__)


def select_quotes(ranked_themes: List[Theme], other_bucket: Theme) -> List[Review]:
    """
    Select exactly 3 verbatim quotes based on the strategy.
    Slot 1: Dominant theme (pain) - rating <= 2, longest
    Slot 2: Dominant theme (praise) - rating >= 4, longest
    Slot 3: Fallback cascade
    """
    quotes = []
    used_ids = set()

    if not ranked_themes:
        return []

    dominant = ranked_themes[0]

    # Slot 1: Pain
    pain_cands = sorted(
        [r for r in dominant.reviews if r.rating <= 2],
        key=lambda r: len(r.text), reverse=True
    )
    if pain_cands:
        quotes.append(pain_cands[0])
        used_ids.add(pain_cands[0].id)

    # Slot 2: Praise
    praise_cands = sorted(
        [r for r in dominant.reviews if r.rating >= 4],
        key=lambda r: len(r.text), reverse=True
    )
    if praise_cands:
        for r in praise_cands:
            if r.id not in used_ids:
                quotes.append(r)
                used_ids.add(r.id)
                break

    # Slot 3: Cascade
    # Next named theme with count >= 1
    slot3_filled = False
    for t in ranked_themes[1:]:
        if t.count >= 1:
            cands = sorted(t.reviews, key=lambda r: len(r.text), reverse=True)
            for r in cands:
                if r.id not in used_ids:
                    quotes.append(r)
                    used_ids.add(r.id)
                    slot3_filled = True
                    break
        if slot3_filled:
            break
            
    if not slot3_filled and other_bucket.count >= 1:
        other_cands = sorted(
            [r for r in other_bucket.reviews if r.rating <= 2],
            key=lambda r: len(r.text), reverse=True
        )
        for r in other_cands:
            if r.id not in used_ids:
                quotes.append(r)
                used_ids.add(r.id)
                slot3_filled = True
                break

    # If we still don't have 3, just fill from any available
    if len(quotes) < 3:
        all_reviews = []
        for t in ranked_themes:
            all_reviews.extend(t.reviews)
        all_reviews.extend(other_bucket.reviews)
        all_reviews.sort(key=lambda r: len(r.text), reverse=True)
        
        for r in all_reviews:
            if r.id not in used_ids:
                quotes.append(r)
                used_ids.add(r.id)
                if len(quotes) == 3:
                    break

    return quotes[:3]


def generate_actions(ranked_themes: List[Theme], other_bucket: Theme) -> List[str]:
    """Generate 3 actions based on templates."""
    actions = []
    
    if len(ranked_themes) >= 1:
        actions.append(ranked_themes[0].action_template or f"Investigate {ranked_themes[0].name} issues.")
    if len(ranked_themes) >= 2:
        actions.append(ranked_themes[1].action_template or f"Investigate {ranked_themes[1].name} issues.")
    elif len(ranked_themes) == 1:
        actions.append(f"Monitor {ranked_themes[0].name} for further feedback.")
        
    # Action 3: from other bucket
    actions.append("Investigate account-blocking reports in the unmatched bucket.")
    
    # Pad if necessary
    while len(actions) < 3:
        actions.append("Continue monitoring user feedback.")
        
    return actions[:3]


def mine_emerging_issue(other_bucket: Theme) -> Optional[str]:
    """Mine the other bucket for an emerging issue."""
    if other_bucket.count == 0:
        return None
        
    return (
        f"{other_bucket.count} reviews did not match any named theme. "
        "Consider reviewing these for potential emerging issues such as account blocking or gold/silver trading."
    )


def build_pulse(ranked_themes: List[Theme], other_bucket: Theme) -> PulseNote:
    """Build the final PulseNote."""
    all_reviews = []
    for t in ranked_themes:
        all_reviews.extend(t.reviews)
    all_reviews.extend(other_bucket.reviews)
    
    if not all_reviews:
        week_ending = "N/A"
    else:
        latest = max(r.date for r in all_reviews)
        week_ending = latest.strftime("%Y-%m-%d")

    quotes = select_quotes(ranked_themes, other_bucket)
    actions = generate_actions(ranked_themes, other_bucket)
    emerging = mine_emerging_issue(other_bucket)

    top_themes = ranked_themes[:3]

    return PulseNote(
        week_ending=week_ending,
        top_themes=top_themes,
        quotes=quotes,
        actions=actions,
        emerging_issue=emerging
    )
