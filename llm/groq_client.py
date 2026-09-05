"""
llm/groq_client.py
------------------
Groq API client and PulseNote enrichment for Phase 4 — Groq LLM Polish.

Public API
----------
    get_groq_client(model)              -> Groq  (or None if key missing)
    call_groq(prompt, system, model, max_tokens) -> str
    enrich_with_llm(pulse, config, dry_run) -> PulseNote
"""

from __future__ import annotations

import logging
import os
import time
from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, Optional

from llm import LLMOutputError
from llm.prompts import build_polish_prompt, parse_groq_response

if TYPE_CHECKING:
    from pulse import PulseNote

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = "llama3-8b-8192"
_MAX_RETRIES   = 3
_BACKOFF_BASE  = 2.0   # seconds; doubles each retry


# ---------------------------------------------------------------------------
# Groq client initialisation
# ---------------------------------------------------------------------------

def get_groq_client(model: str = _DEFAULT_MODEL):
    """
    Initialise and return a ``groq.Groq`` client.

    Looks for the API key in order:
    1. ``GROQ_API_KEY`` environment variable
    2. ``credentials/groq_api_key.txt`` file in the project root

    Parameters
    ----------
    model : str
        Model identifier (used only for logging here; passed at call time).

    Returns
    -------
    groq.Groq or None
        Returns ``None`` if the key is not found, so callers can fall back
        gracefully without raising.
    """
    api_key = _resolve_api_key()
    if not api_key:
        logger.warning(
            "GROQ_API_KEY not found in environment or credentials/groq_api_key.txt. "
            "Groq LLM polish will be skipped."
        )
        return None

    try:
        from groq import Groq  # type: ignore[import]
        client = Groq(api_key=api_key)
        logger.info("Groq client initialised (model=%s).", model)
        return client
    except ImportError:
        logger.warning(
            "groq package not installed. Run: pip install groq>=0.9. "
            "Falling back to Phase 3 rule-based output."
        )
        return None


def _resolve_api_key() -> Optional[str]:
    """Return GROQ_API_KEY from env or credentials file, or None."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # 1. Environment variable
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key

    # 2. credentials/groq_api_key.txt
    cred_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "credentials", "groq_api_key.txt",
    )
    if os.path.exists(cred_path):
        with open(cred_path, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key

    return None


# ---------------------------------------------------------------------------
# Low-level API call with retry
# ---------------------------------------------------------------------------

def call_groq(
    user_prompt: str,
    system_prompt: str,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 600,
) -> str:
    """
    Make a single-turn Groq chat completion call with exponential-backoff retry.

    Parameters
    ----------
    user_prompt : str
    system_prompt : str
    model : str
        Groq model ID (e.g. ``"llama3-8b-8192"``).
    max_tokens : int
        Hard cap on response length.

    Returns
    -------
    str
        Raw text content of the model's first message.

    Raises
    ------
    RuntimeError
        If all retries are exhausted.
    ImportError
        If the ``groq`` package is not installed.
    """
    from groq import Groq, RateLimitError  # type: ignore[import]

    # Enforce TPM limit (15k)
    max_tokens = min(max_tokens, 15000)

    api_key = _resolve_api_key()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    client = Groq(api_key=api_key)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    last_exc: Exception = RuntimeError("call_groq: no attempts made")
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,   # low temp for deterministic, factual output
            )
            content = response.choices[0].message.content or ""
            logger.info(
                "Groq call succeeded (attempt %d/%d, model=%s, tokens=%s).",
                attempt, _MAX_RETRIES, model,
                response.usage.total_tokens if response.usage else "?",
            )
            return content

        except RateLimitError as exc:
            wait = _BACKOFF_BASE ** attempt
            logger.warning(
                "Groq RateLimitError on attempt %d/%d. Retrying in %.1fs…",
                attempt, _MAX_RETRIES, wait,
            )
            last_exc = exc
            time.sleep(wait)

        except Exception as exc:
            logger.error("Groq API error on attempt %d/%d: %s", attempt, _MAX_RETRIES, exc)
            last_exc = exc
            break

    raise RuntimeError(
        f"Groq call failed after {_MAX_RETRIES} attempts: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# PulseNote enrichment (Phase 4 main entry point)
# ---------------------------------------------------------------------------

def enrich_with_llm(
    pulse: "PulseNote",
    config: dict,
    dry_run: bool = False,
) -> "PulseNote":
    """
    Enrich a Phase 3 ``PulseNote`` with Groq-polished action ideas and email
    metadata.

    Behaviour
    ---------
    * Builds the prompt (quotes intentionally excluded from input).
    * Calls Groq and parses the JSON response.
    * Returns a **new** ``PulseNote`` with:
      - ``actions``       — replaced with Groq-polished versions
      - ``email_subject`` — set by Groq
      - ``email_intro``   — set by Groq
      - ``quotes``        — carried over verbatim, never modified
    * On any failure (missing key, rate-limit exhausted, ``--dry-run``,
      ``LLMOutputError``): logs a WARNING and returns the original pulse
      with fallback ``email_subject`` / ``email_intro`` filled in.

    Parameters
    ----------
    pulse : PulseNote
        Phase 3 output.
    config : dict
        Parsed config.yaml (used to read ``groq_model``).
    dry_run : bool
        If True, skip the Groq call entirely.

    Returns
    -------
    PulseNote
        Enriched pulse (or original with fallback metadata on failure).
    """
    if dry_run:
        logger.warning("Groq unavailable — using Phase 3 rule-based output as fallback (dry-run).")
        return _apply_fallback(pulse)

    model = config.get("groq_model", _DEFAULT_MODEL)
    client = get_groq_client(model)
    if client is None:
        return _apply_fallback(pulse)

    system_prompt, user_prompt = build_polish_prompt(pulse)

    try:
        raw = call_groq(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            model=model,
            max_tokens=600,
        )
        parsed = parse_groq_response(raw)
    except (RuntimeError, LLMOutputError, Exception) as exc:
        logger.warning(
            "Groq unavailable — using Phase 3 rule-based output as fallback. Reason: %s", exc
        )
        return _apply_fallback(pulse)

    # Build enriched PulseNote — quotes are carried over verbatim
    enriched = deepcopy(pulse)
    enriched.actions       = [a.strip() for a in parsed["actions"]]
    enriched.email_subject = parsed["email_subject"].strip()
    enriched.email_intro   = parsed["email_intro"].strip()

    logger.info("Groq polish applied: actions rewritten, email metadata set.")
    return enriched


def _apply_fallback(pulse: "PulseNote") -> "PulseNote":
    """Return a copy of *pulse* with deterministic fallback email metadata."""
    enriched = deepcopy(pulse)
    if not enriched.email_subject:
        enriched.email_subject = (
            f"Weekly App Feedback Pulse \u2014 Week ending {pulse.week_ending}"
        )
    if not enriched.email_intro:
        # Use the first non-empty line of the markdown as the intro
        for line in pulse.as_markdown().splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                enriched.email_intro = line
                break
    return enriched
