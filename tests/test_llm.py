"""
tests/test_llm.py
-----------------
Unit tests for Phase 4 — Groq LLM Polish.

All tests are fully mockable — no live Groq API call is made.

Run with:
    python -m pytest tests/test_llm.py -v
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ingestion import Review
from llm import LLMOutputError
from llm.prompts import build_polish_prompt, parse_groq_response
from llm.groq_client import enrich_with_llm, _apply_fallback
from pulse import PulseNote
from themes import Theme


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE = datetime(2026, 8, 30, tzinfo=timezone.utc)


def _review(text: str, rid: str = "r1", rating: int = 2) -> Review:
    return Review(
        id=rid, source="app_store", rating=rating,
        title="", text=text, date=_DATE,
    )


def _theme(name: str, n: int = 5) -> Theme:
    t = Theme(name=name, keywords=[], action_template=f"Fix {name} issues.")
    t.reviews = [
        _review(f"Long enough review text for {name} issue number {i}", f"{name}-{i}")
        for i in range(n)
    ]
    return t


def _make_pulse(actions: list[str] | None = None) -> PulseNote:
    themes = [_theme("payments", 76), _theme("onboarding", 2), _theme("kyc", 1)]
    quotes = [
        _review("I sold my silver and the amount was never credited to my bank account.", "q1", rating=1),
        _review("No other UPI service can beat the speed of PhonePe in low network areas.", "q2", rating=5),
        _review("My account has been blocked for security reasons despite submitting all documents.", "q3", rating=3),
    ]
    return PulseNote(
        week_ending="2026-08-30",
        top_themes=themes,
        quotes=quotes,
        actions=actions or [
            "Investigate the top payment failure reason and add a retry option.",
            "Add NRI registration support for international numbers.",
            "Investigate account-blocking reports in the unmatched bucket.",
        ],
        emerging_issue="49 reviews did not match any named theme. Top signal: account blocking.",
    )


# ---------------------------------------------------------------------------
# parse_groq_response
# ---------------------------------------------------------------------------

class TestParseGroqResponse:

    def _valid_json(self, **overrides) -> str:
        data = {
            "actions": ["Action one here", "Action two here", "Action three here"],
            "email_subject": "Weekly App Feedback Pulse",
            "email_intro": "This week payments dominated feedback with 76 reviews.",
        }
        data.update(overrides)
        return json.dumps(data)

    def test_parse_valid_groq_response(self):
        result = parse_groq_response(self._valid_json())
        assert result["actions"] == ["Action one here", "Action two here", "Action three here"]
        assert result["email_subject"] == "Weekly App Feedback Pulse"
        assert "payments" in result["email_intro"]

    def test_parse_strips_json_fences(self):
        raw = "```json\n" + self._valid_json() + "\n```"
        result = parse_groq_response(raw)
        assert len(result["actions"]) == 3

    def test_parse_missing_actions_raises(self):
        raw = json.dumps({"email_subject": "Sub", "email_intro": "Intro"})
        with pytest.raises(LLMOutputError, match="missing required keys"):
            parse_groq_response(raw)

    def test_parse_wrong_action_count_raises(self):
        raw = self._valid_json(actions=["only one action"])
        with pytest.raises(LLMOutputError, match="list of exactly 3"):
            parse_groq_response(raw)

    def test_parse_empty_action_string_raises(self):
        raw = self._valid_json(actions=["Action 1", "", "Action 3"])
        with pytest.raises(LLMOutputError, match="non-empty strings"):
            parse_groq_response(raw)

    def test_parse_empty_subject_raises(self):
        raw = self._valid_json(email_subject="   ")
        with pytest.raises(LLMOutputError, match="email_subject"):
            parse_groq_response(raw)

    def test_parse_non_json_raises(self):
        with pytest.raises(LLMOutputError, match="not valid JSON"):
            parse_groq_response("this is not json at all")

    def test_parse_non_dict_raises(self):
        with pytest.raises(LLMOutputError, match="not a JSON object"):
            parse_groq_response("[1, 2, 3]")

    def test_parse_missing_email_intro_raises(self):
        raw = json.dumps({
            "actions": ["A1", "A2", "A3"],
            "email_subject": "Subject",
        })
        with pytest.raises(LLMOutputError, match="missing required keys"):
            parse_groq_response(raw)


# ---------------------------------------------------------------------------
# build_polish_prompt
# ---------------------------------------------------------------------------

class TestBuildPolishPrompt:

    def test_prompt_excludes_quotes(self):
        """The user prompt must NOT contain any verbatim review text."""
        pulse = _make_pulse()
        _, user_prompt = build_polish_prompt(pulse)
        for review in pulse.quotes:
            # Check first 40 chars of each quote are absent from the prompt
            assert review.text[:40] not in user_prompt, (
                f"Quote text leaked into user prompt: {review.text[:40]!r}"
            )

    def test_prompt_includes_theme_names(self):
        pulse = _make_pulse()
        _, user_prompt = build_polish_prompt(pulse)
        assert "Payments" in user_prompt
        assert "76" in user_prompt   # review count

    def test_prompt_includes_week_ending(self):
        pulse = _make_pulse()
        _, user_prompt = build_polish_prompt(pulse)
        assert pulse.week_ending in user_prompt

    def test_prompt_includes_existing_actions(self):
        pulse = _make_pulse()
        _, user_prompt = build_polish_prompt(pulse)
        assert "retry option" in user_prompt   # from action template

    def test_system_prompt_forbids_quote_alteration(self):
        pulse = _make_pulse()
        system_prompt, _ = build_polish_prompt(pulse)
        assert "quote" in system_prompt.lower()

    def test_returns_tuple_of_two_strings(self):
        pulse = _make_pulse()
        result = build_polish_prompt(pulse)
        assert isinstance(result, tuple) and len(result) == 2
        assert all(isinstance(s, str) for s in result)


# ---------------------------------------------------------------------------
# enrich_with_llm
# ---------------------------------------------------------------------------

class TestEnrichWithLLM:

    _POLISHED_RESPONSE = json.dumps({
        "actions": [
            "Add real-time payment failure diagnostics with a one-tap retry flow.",
            "Enable international phone number registration to support NRI users.",
            "Introduce a self-service account unblocking flow with document re-upload.",
        ],
        "email_subject": "Weekly PhonePe Feedback Pulse — Aug 30",
        "email_intro": (
            "This week, payment reliability dominated user feedback with 76 reviews. "
            "Here are this week's top signals and recommended next steps."
        ),
    })

    def _config(self) -> dict:
        return {"groq_model": "llama3-8b-8192"}

    def test_enrich_preserves_quotes(self):
        """Quotes must be byte-for-byte identical before and after enrichment."""
        pulse = _make_pulse()
        original_quotes = deepcopy(pulse.quotes)

        with patch("llm.groq_client.call_groq", return_value=self._POLISHED_RESPONSE):
            with patch("llm.groq_client.get_groq_client", return_value=MagicMock()):
                enriched = enrich_with_llm(pulse, self._config())

        assert len(enriched.quotes) == len(original_quotes)
        for orig, enr in zip(original_quotes, enriched.quotes):
            assert orig.text == enr.text, f"Quote text was altered: {orig.text!r} -> {enr.text!r}"
            assert orig.id   == enr.id

    def test_enrich_replaces_actions(self):
        pulse = _make_pulse()
        with patch("llm.groq_client.call_groq", return_value=self._POLISHED_RESPONSE):
            with patch("llm.groq_client.get_groq_client", return_value=MagicMock()):
                enriched = enrich_with_llm(pulse, self._config())

        assert len(enriched.actions) == 3
        assert "one-tap retry" in enriched.actions[0]

    def test_enrich_sets_email_metadata(self):
        pulse = _make_pulse()
        with patch("llm.groq_client.call_groq", return_value=self._POLISHED_RESPONSE):
            with patch("llm.groq_client.get_groq_client", return_value=MagicMock()):
                enriched = enrich_with_llm(pulse, self._config())

        assert "PhonePe" in enriched.email_subject
        assert len(enriched.email_intro) > 0

    def test_fallback_on_missing_api_key(self):
        """When no API key is set, original pulse is returned with fallback metadata."""
        pulse = _make_pulse()
        with patch("llm.groq_client._resolve_api_key", return_value=None):
            enriched = enrich_with_llm(pulse, self._config())

        # Original actions preserved
        assert enriched.actions == pulse.actions
        # Fallback email subject populated
        assert pulse.week_ending in enriched.email_subject

    def test_fallback_on_dry_run(self):
        pulse = _make_pulse()
        enriched = enrich_with_llm(pulse, self._config(), dry_run=True)
        # Actions unchanged
        assert enriched.actions == pulse.actions
        # Email metadata filled in
        assert enriched.email_subject != ""
        assert enriched.email_intro != ""

    def test_fallback_on_llm_output_error(self):
        pulse = _make_pulse()
        with patch("llm.groq_client.call_groq", return_value="not valid json {{{{"):
            with patch("llm.groq_client.get_groq_client", return_value=MagicMock()):
                enriched = enrich_with_llm(pulse, self._config())

        # Should fall back gracefully
        assert enriched.actions == pulse.actions

    def test_original_pulse_not_mutated(self):
        """enrich_with_llm must not mutate the input PulseNote in-place."""
        pulse = _make_pulse()
        original_actions = list(pulse.actions)

        with patch("llm.groq_client.call_groq", return_value=self._POLISHED_RESPONSE):
            with patch("llm.groq_client.get_groq_client", return_value=MagicMock()):
                enrich_with_llm(pulse, self._config())

        assert pulse.actions == original_actions


# ---------------------------------------------------------------------------
# _apply_fallback
# ---------------------------------------------------------------------------

class TestApplyFallback:

    def test_sets_default_email_subject(self):
        pulse = _make_pulse()
        result = _apply_fallback(pulse)
        assert "2026-08-30" in result.email_subject

    def test_sets_email_intro_from_markdown(self):
        pulse = _make_pulse()
        result = _apply_fallback(pulse)
        assert len(result.email_intro) > 0

    def test_does_not_overwrite_existing_subject(self):
        pulse = _make_pulse()
        pulse.email_subject = "Already set"
        result = _apply_fallback(pulse)
        assert result.email_subject == "Already set"
