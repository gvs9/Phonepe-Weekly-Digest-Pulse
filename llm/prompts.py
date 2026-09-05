"""
llm/prompts.py
--------------
Prompt builder and response validator for the Groq LLM Polish step (Phase 4).

Public API
----------
    build_polish_prompt(pulse)          -> (system_prompt, user_prompt)
    parse_groq_response(raw)            -> dict
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from llm import LLMOutputError

if TYPE_CHECKING:
    from pulse import PulseNote

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"actions", "email_subject", "email_intro"}

_SYSTEM_PROMPT = """\
You are a concise editorial assistant for a mobile-app product team.
Your job is to improve the clarity and tone of a weekly user-feedback pulse note.

Rules you MUST follow:
1. Return ONLY a valid JSON object — no markdown fences, no extra text.
2. The JSON must contain exactly these three keys:
   - "actions": a JSON array of exactly 3 short action strings (each ≤ 25 words)
   - "email_subject": a single subject line string (≤ 12 words)
   - "email_intro": a 1-2 sentence email opener string (≤ 40 words)
3. Do NOT invent, alter, or paraphrase any user quote — quotes are never in your input.
4. Keep the total response under 600 tokens.
5. Actions must be specific, concrete, and directly traceable to the theme data provided.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_polish_prompt(pulse: "PulseNote") -> tuple[str, str]:
    """
    Build the (system_prompt, user_prompt) pair for the Groq polish call.

    Design decisions
    ----------------
    * User quotes are **deliberately excluded** from the prompt — they are
      injected verbatim into the final PulseNote *after* Groq returns, so the
      LLM has zero opportunity to alter or hallucinate them.
    * The user prompt is compact: theme names + counts, raw actions, and the
      emerging-issue text (if any).

    Parameters
    ----------
    pulse : PulseNote
        The Phase 3 pulse (pre-LLM).

    Returns
    -------
    tuple[str, str]
        ``(system_prompt, user_prompt)``
    """
    theme_lines = "\n".join(
        f"  - {t.name.title()}: {t.count} reviews" for t in pulse.top_themes
    )
    action_lines = "\n".join(
        f"  {i}. {a}" for i, a in enumerate(pulse.actions, 1)
    )
    emerging = pulse.emerging_issue or "None"

    user_prompt = f"""\
Week ending: {pulse.week_ending}

Top themes (name: review count):
{theme_lines}

Current rule-based action ideas (rewrite these to be more specific and actionable):
{action_lines}

Emerging issue from unmatched reviews:
  {emerging}

Rewrite the 3 action ideas to be context-aware and specific to the theme data above.
Also write an email subject line and a short 1-2 sentence email intro for the weekly pulse.

Respond ONLY with a JSON object matching this schema:
{{
  "actions": ["<action 1>", "<action 2>", "<action 3>"],
  "email_subject": "<subject line>",
  "email_intro": "<1-2 sentence email opener>"
}}"""

    return _SYSTEM_PROMPT, user_prompt


def parse_groq_response(raw: str) -> dict:
    """
    JSON-parse and schema-validate a raw Groq response string.

    Parameters
    ----------
    raw : str
        Raw string returned by the Groq API.

    Returns
    -------
    dict
        Validated response with keys: ``actions``, ``email_subject``, ``email_intro``.

    Raises
    ------
    LLMOutputError
        If the response is not valid JSON, missing required keys, or has wrong
        value types.
    """
    # Strip common LLM preamble (```json ... ```)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMOutputError(
            f"Groq response is not valid JSON: {exc}\nRaw response:\n{raw[:500]}"
        ) from exc

    if not isinstance(data, dict):
        raise LLMOutputError(
            f"Groq response is not a JSON object. Got: {type(data).__name__}"
        )

    missing = _REQUIRED_KEYS - set(data.keys())
    if missing:
        raise LLMOutputError(
            f"Groq response missing required keys: {missing}\nRaw response:\n{raw[:500]}"
        )

    # Validate types
    actions = data["actions"]
    if not isinstance(actions, list) or len(actions) != 3:
        raise LLMOutputError(
            f"'actions' must be a list of exactly 3 strings. Got: {actions!r}"
        )
    if not all(isinstance(a, str) and a.strip() for a in actions):
        raise LLMOutputError(
            f"'actions' must contain non-empty strings. Got: {actions!r}"
        )

    for key in ("email_subject", "email_intro"):
        val = data[key]
        if not isinstance(val, str) or not val.strip():
            raise LLMOutputError(
                f"'{key}' must be a non-empty string. Got: {val!r}"
            )

    logger.debug("parse_groq_response: validated successfully.")
    return data
