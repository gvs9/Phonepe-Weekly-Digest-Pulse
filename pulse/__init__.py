"""
pulse/__init__.py
-----------------
PulseNote dataclass — the canonical output of the Pulse Generator (Phase 3)
and the input to Groq LLM Polish (Phase 4).

Fields
------
week_ending      : str            — ISO date of the latest review in the dataset
top_themes       : List[Theme]    — ranked themes (Phase 2 output, top 3)
quotes           : List[Review]   — exactly 3 verbatim review objects
actions          : List[str]      — exactly 3 action ideas (Phase 3 templates / Phase 4 polish)
emerging_issue   : Optional[str]  — one-sentence summary of [other] bucket signal
email_subject    : str            — set by Phase 4; fallback generated if Groq unavailable
email_intro      : str            — 1-2 sentence email opener; set by Phase 4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ingestion import Review
    from themes import Theme


@dataclass
class PulseNote:
    """
    The structured one-page weekly pulse.

    Produced by ``pulse.generator.build_pulse()`` (Phase 3) and optionally
    enriched by ``llm.groq_client.enrich_with_llm()`` (Phase 4).
    """

    week_ending: str                    # "YYYY-MM-DD"
    top_themes: List["Theme"]
    quotes: List["Review"]              # always exactly 3, verbatim
    actions: List[str]                  # always exactly 3
    emerging_issue: Optional[str] = None
    email_subject: str = ""
    email_intro: str = ""

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def as_markdown(self) -> str:
        """
        Render the pulse as a canonical markdown document.

        Structure
        ---------
        # Weekly Pulse — Week ending YYYY-MM-DD
        ## Top Themes
        ## User Voices
        ## Action Ideas
        ## Emerging Issue   (omitted when emerging_issue is None)
        """
        lines: list[str] = []

        lines.append(f"# Weekly Pulse \u2014 Week ending {self.week_ending}")
        lines.append("")

        # --- Top Themes ---
        lines.append("## Top Themes")
        for i, theme in enumerate(self.top_themes, 1):
            lines.append(f"{i}. **{theme.name.title()}** ({theme.count} reviews)")
        lines.append("")

        # --- User Voices ---
        lines.append("## User Voices")
        for review in self.quotes:
            # Truncate to first 300 chars for readability; still verbatim
            text = review.text[:300].strip()
            if len(review.text) > 300:
                text += "..."
            date_str = review.date.strftime("%Y-%m-%d")
            lines.append(f'- "{text}" \u2014 {review.stars}, {date_str}')
        lines.append("")

        # --- Action Ideas ---
        lines.append("## Action Ideas")
        for i, action in enumerate(self.actions, 1):
            lines.append(f"{i}. {action}")
        lines.append("")

        # --- Emerging Issue (optional) ---
        if self.emerging_issue:
            lines.append("## Emerging Issue")
            lines.append(self.emerging_issue)
            lines.append("")

        return "\n".join(lines)

    def as_plain_text(self) -> str:
        """
        Plain-text version for the Gmail email body (Phase 6).
        Strips markdown formatting; keeps structure readable.
        """
        md = self.as_markdown()
        # Strip leading #/- markers
        plain = []
        for line in md.splitlines():
            line = line.lstrip("# ").lstrip("- ")
            plain.append(line)
        return "\n".join(plain)

    def __str__(self) -> str:  # pragma: no cover
        return self.as_markdown()
