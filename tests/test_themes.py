"""
tests/test_themes.py
---------------------
Unit tests for Phase 2 — Thematic Grouping.

Run with:
    python -m pytest tests/ -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ingestion import ConfigError, Review
from themes import OTHER, Theme, ThemeConfig
from themes.clusterer import _matches_any, assign_themes, rank_themes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE = datetime(2024, 6, 1, tzinfo=timezone.utc)


def _review(text: str, rid: str = "r1", title: str = "", rating: int = 3) -> Review:
    return Review(id=rid, source="app_store", rating=rating, title=title, text=text, date=_DATE)


def _make_config(*theme_tuples) -> ThemeConfig:
    """Build a ThemeConfig from (name, [keywords], action_template) tuples."""
    raw = [
        {"name": name, "keywords": kws, "action_template": action}
        for name, kws, action in theme_tuples
    ]
    return ThemeConfig(raw)


# ---------------------------------------------------------------------------
# ThemeConfig — model & validation
# ---------------------------------------------------------------------------

class TestThemeConfig:

    def test_loads_valid_themes(self):
        cfg = _make_config(
            ("payments", ["pay", "payment"], "Fix payments"),
            ("onboarding", ["signup", "register"], "Fix onboarding"),
        )
        assert len(cfg) == 2
        assert cfg.themes[0].name == "payments"
        assert "pay" in cfg.themes[0].keywords

    def test_keywords_lowercased(self):
        cfg = _make_config(("payments", ["Pay", "PAYMENT"], ""))
        assert cfg.themes[0].keywords == ["pay", "payment"]

    def test_empty_keywords_allowed(self):
        cfg = _make_config(("payments", [], ""))
        assert cfg.themes[0].keywords == []

    def test_max_five_themes_allowed(self):
        themes = [(f"theme{i}", ["kw"], "") for i in range(5)]
        cfg = ThemeConfig([{"name": n, "keywords": k, "action_template": a} for n, k, a in themes])
        assert len(cfg) == 5

    def test_more_than_five_raises_config_error(self):
        raw = [{"name": f"t{i}", "keywords": [], "action_template": ""} for i in range(6)]
        with pytest.raises(ConfigError, match="maximum allowed is 5"):
            ThemeConfig(raw)

    def test_non_list_raises_config_error(self):
        with pytest.raises(ConfigError, match="must be a list"):
            ThemeConfig("not a list")  # type: ignore

    def test_missing_name_raises_config_error(self):
        with pytest.raises(ConfigError, match="non-empty 'name'"):
            ThemeConfig([{"keywords": ["pay"], "action_template": ""}])

    def test_from_config_factory(self):
        cfg = ThemeConfig.from_config({
            "themes": [{"name": "payments", "keywords": ["pay"], "action_template": ""}]
        })
        assert len(cfg) == 1

    def test_from_config_missing_themes_key_raises(self):
        with pytest.raises(ConfigError, match="missing the required 'themes' key"):
            ThemeConfig.from_config({})

    def test_theme_count_property(self):
        t = Theme(name="payments", keywords=["pay"])
        assert t.count == 0
        t.reviews.append(_review("pay now this is a long enough review text here", "r1"))
        assert t.count == 1


# ---------------------------------------------------------------------------
# _matches_any — internal helper
# ---------------------------------------------------------------------------

class TestMatchesAny:

    def test_exact_match(self):
        assert _matches_any("payment failed today", ["payment"]) is True

    def test_substring_match(self):
        assert _matches_any("i made a payment today", ["pay"]) is True

    def test_multi_word_keyword(self):
        assert _matches_any("first time signing up here", ["first time"]) is True

    def test_case_already_lower(self):
        # caller lowercases both sides; function receives lowercase
        assert _matches_any("great app overall", ["great"]) is True

    def test_no_match(self):
        assert _matches_any("nothing relevant here at all", ["payment", "kyc"]) is False

    def test_empty_keywords(self):
        assert _matches_any("any text here", []) is False

    def test_empty_text(self):
        assert _matches_any("", ["pay"]) is False


# ---------------------------------------------------------------------------
# assign_themes — core assignment logic
# ---------------------------------------------------------------------------

class TestAssignThemes:

    def _cfg(self) -> ThemeConfig:
        return _make_config(
            ("payments",   ["pay", "payment", "transaction"],  "Fix payments"),
            ("onboarding", ["signup", "register", "first time"], "Fix onboarding"),
            ("kyc",        ["kyc", "verify", "verification"],   "Fix KYC"),
        )

    def test_basic_assignment(self):
        reviews = [
            _review("My payment failed and the transaction did not go through", "r1"),
            _review("Signing up was easy and the first time experience was great", "r2"),
        ]
        themes = assign_themes(reviews, self._cfg())
        named = {t.name: t for t in themes if t.name != OTHER}
        assert named["payments"].count == 1
        assert named["onboarding"].count == 1
        assert named["payments"].reviews[0].id == "r1"

    def test_first_matching_theme_wins(self):
        """Review matching both 'payments' and 'kyc' → assigned to 'payments' (config order)."""
        cfg = _make_config(
            ("payments", ["pay"],  ""),
            ("kyc",      ["kyc"],  ""),
        )
        # "payment" contains "pay"; "kyc" also present → payments wins (config order)
        r = _review("My payment for kyc verification failed multiple times today", "r1")
        themes = assign_themes([r], cfg)
        named = {t.name: t for t in themes}
        assert named["payments"].count == 1
        assert named["kyc"].count == 0

    def test_unmatched_goes_to_other(self):
        r = _review("The weather today is really nice and sunny outside", "r1")
        themes = assign_themes([r], self._cfg())
        other = next(t for t in themes if t.name == OTHER)
        assert other.count == 1
        assert other.reviews[0].id == "r1"

    def test_review_theme_attribute_set(self):
        r = _review("payment failed and money was deducted without any result", "r1")
        assign_themes([r], self._cfg())
        assert r.theme == "payments"

    def test_unmatched_review_theme_attribute(self):
        r = _review("completely unrelated topic about something else entirely here", "r1")
        assign_themes([r], self._cfg())
        assert r.theme == OTHER

    def test_case_insensitive_matching(self):
        """Keywords are stored lowercase; searchable_text() is lowercase — match must work."""
        r = _review("KYC VERIFICATION took three days with zero updates at all", "r1")
        themes = assign_themes([r], self._cfg())
        named = {t.name: t for t in themes}
        assert named["kyc"].count == 1

    def test_title_contributes_to_matching(self):
        """Keyword in title field should count."""
        r = _review(
            "This is a very long review body that has no matching words at all",
            rid="r1",
            title="Payment Issue",
        )
        themes = assign_themes([r], self._cfg())
        named = {t.name: t for t in themes}
        assert named["payments"].count == 1

    def test_multi_word_keyword_match(self):
        r = _review("The first time setup was confusing and took a long time", "r1")
        themes = assign_themes([r], self._cfg())
        named = {t.name: t for t in themes}
        assert named["onboarding"].count == 1

    def test_empty_reviews_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            assign_themes([], self._cfg())

    def test_other_bucket_always_last(self):
        reviews = [_review("payment failed and the transfer did not go through at all", "r1")]
        themes = assign_themes(reviews, self._cfg())
        assert themes[-1].name == OTHER

    def test_idempotent_reassignment(self):
        """Calling assign_themes twice resets counts correctly."""
        reviews = [_review("payment failed again and again every single time I try", "r1")]
        cfg = self._cfg()
        assign_themes(reviews, cfg)
        assign_themes(reviews, cfg)   # second call
        named = {t.name: t for t in cfg}
        assert named["payments"].count == 1   # not doubled

    def test_all_assigned_total_equals_input(self):
        reviews = [
            _review("my payment keeps failing every single time I try it", f"r{i}")
            for i in range(10)
        ]
        themes = assign_themes(reviews, self._cfg())
        total = sum(t.count for t in themes)
        assert total == len(reviews)


# ---------------------------------------------------------------------------
# rank_themes
# ---------------------------------------------------------------------------

class TestRankThemes:

    def _make_themes(self, counts: dict[str, int]) -> list[Theme]:
        result = []
        for name, n in counts.items():
            t = Theme(name=name, keywords=[])
            t.reviews = [
                _review(f"long enough review text for theme {name} review number {i}", f"{name}-{i}")
                for i in range(n)
            ]
            result.append(t)
        return result

    def test_sorted_descending_by_count(self):
        themes = self._make_themes({"payments": 5, "onboarding": 10, "kyc": 2})
        ranked = rank_themes(themes)
        assert [t.name for t in ranked] == ["onboarding", "payments", "kyc"]

    def test_other_excluded(self):
        themes = self._make_themes({"payments": 3, OTHER: 7})
        ranked = rank_themes(themes)
        assert all(t.name != OTHER for t in ranked)
        assert len(ranked) == 1

    def test_empty_input(self):
        assert rank_themes([]) == []

    def test_only_other_returns_empty(self):
        themes = self._make_themes({OTHER: 5})
        assert rank_themes(themes) == []

    def test_ties_preserved(self):
        """Themes with equal counts should both appear in the result."""
        themes = self._make_themes({"payments": 3, "kyc": 3})
        ranked = rank_themes(themes)
        assert len(ranked) == 2
        assert ranked[0].count == ranked[1].count == 3
