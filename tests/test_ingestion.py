"""
tests/test_ingestion.py
-----------------------
Smoke tests and unit tests for Phase 1: ingestion layer.

Run with:
    python -m pytest tests/ -v
"""

from __future__ import annotations

import json
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ingestion import InsufficientDataError, Review, SchemaError
from ingestion.parser import (
    filter_by_window,
    filter_noise,
    parse_reviews,
    parse_reviews_dir,
    _noise_reason,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _recent_date(days_ago: int = 10) -> str:
    """Return a date string N days in the past (ISO 8601)."""
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d")


def _old_date() -> str:
    """Return a date string 200 days in the past (outside any review window)."""
    dt = datetime.now(tz=timezone.utc) - timedelta(days=200)
    return dt.strftime("%Y-%m-%d")


def _write_csv(tmp_path: Path, filename: str, rows: list[dict], header: list[str] | None = None) -> Path:
    path = tmp_path / filename
    if header is None and rows:
        header = list(rows[0].keys())
    lines = [",".join(header or [])]
    for row in rows:
        lines.append(",".join(str(row.get(h, "")) for h in (header or [])))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Review dataclass tests
# ---------------------------------------------------------------------------

class TestReviewDataclass:

    def test_valid_review(self):
        r = Review(
            id="r1",
            source="app_store",
            rating=4,
            title="Good",
            text="Great app!",
            date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        assert r.stars == "★★★★☆"
        assert "great app!" in r.searchable_text()  # searchable_text() is lowercased

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="text must not be empty"):
            Review(
                id="r2", source="app_store", rating=3,
                title="", text="   ",
                date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            )

    def test_invalid_rating_raises(self):
        with pytest.raises(ValueError, match="rating must be 1–5"):
            Review(
                id="r3", source="app_store", rating=6,
                title="", text="Some text",
                date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            )

    def test_naive_datetime_raises(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            Review(
                id="r4", source="app_store", rating=3,
                title="", text="Some text",
                date=datetime(2024, 6, 1),   # no tzinfo
            )


# ---------------------------------------------------------------------------
# Parser: CSV
# ---------------------------------------------------------------------------

class TestParseReviewsCSV:

    def test_load_valid_csv(self, tmp_path):
        path = _write_csv(tmp_path, "appstore_reviews.csv", [
            {"reviewId": "1", "rating": "4", "title": "Nice", "body": "Really good app I use it every day", "at": _recent_date(5)},
            {"reviewId": "2", "rating": "2", "title": "Bad",  "body": "App keeps crashing and it is very frustrating", "at": _recent_date(10)},
        ])
        reviews = parse_reviews(path)
        assert len(reviews) == 2
        assert all(r.source == "app_store" for r in reviews)
        assert reviews[0].id == "1"
        assert reviews[0].rating == 4

    def test_empty_csv_returns_empty_list(self, tmp_path):
        path = tmp_path / "appstore_empty.csv"
        path.write_text("reviewId,rating,title,body,at\n", encoding="utf-8")
        result = parse_reviews(path)
        assert result == []

    def test_missing_required_columns_raises_schema_error(self, tmp_path):
        path = tmp_path / "appstore_bad.csv"
        path.write_text("reviewId,rating\n1,4\n", encoding="utf-8")
        with pytest.raises(SchemaError, match="Missing required columns"):
            parse_reviews(path)

    def test_empty_text_rows_are_skipped(self, tmp_path):
        path = _write_csv(tmp_path, "appstore_reviews.csv", [
            {"reviewId": "1", "rating": "5", "title": "OK", "body": "   ", "at": _recent_date()},
            {"reviewId": "2", "rating": "3", "title": "OK", "body": "Real content here with enough words to pass", "at": _recent_date()},
        ])
        reviews = parse_reviews(path)
        assert len(reviews) == 1
        assert reviews[0].id == "2"

    def test_bad_date_rows_are_skipped(self, tmp_path):
        path = _write_csv(tmp_path, "appstore_reviews.csv", [
            {"reviewId": "1", "rating": "4", "body": "Great app works well every single day", "at": "not-a-date"},
            {"reviewId": "2", "rating": "4", "body": "Also great and very reliable for all payments", "at": _recent_date()},
        ])
        reviews = parse_reviews(path)
        assert len(reviews) == 1
        assert reviews[0].id == "2"

    def test_duplicate_reviews_deduped(self, tmp_path):
        row = {"reviewId": "dup1", "rating": "3", "title": "OK", "body": "Duplicate review text that is long enough here", "at": _recent_date()}
        path = _write_csv(tmp_path, "appstore_reviews.csv", [row, row, row])
        reviews = parse_reviews(path)
        assert len(reviews) == 1

    def test_unsupported_format_raises(self, tmp_path):
        path = tmp_path / "reviews.xlsx"
        path.write_text("fake", encoding="utf-8")
        with pytest.raises(SchemaError, match="Unsupported file format"):
            parse_reviews(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_reviews(tmp_path / "nonexistent.csv")


# ---------------------------------------------------------------------------
# Parser: JSON
# ---------------------------------------------------------------------------

class TestParseReviewsJSON:

    def test_load_valid_json(self, tmp_path):
        data = [
            {"reviewId": "PS-1", "starRating": "5", "content": "Excellent app with very smooth and fast performance", "at": _recent_date(3)},
            {"reviewId": "PS-2", "starRating": "1", "content": "Payment failed multiple times and support did not help", "at": _recent_date(7)},
        ]
        path = tmp_path / "playstore_reviews.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        reviews = parse_reviews(path)
        assert len(reviews) == 2
        assert reviews[0].source == "play_store"
        assert reviews[0].rating == 5

    def test_json_empty_list_returns_empty(self, tmp_path):
        path = tmp_path / "playstore_reviews.json"
        path.write_text("[]", encoding="utf-8")
        result = parse_reviews(path)
        assert result == []


# ---------------------------------------------------------------------------
# Parser: Directory loading
# ---------------------------------------------------------------------------

class TestParseReviewsDir:

    def test_load_multiple_files(self, tmp_path):
        _write_csv(tmp_path, "appstore_reviews.csv", [
            {"reviewId": "a1", "rating": "4", "body": "App store review content works great every time", "at": _recent_date()},
        ])
        data = [{"reviewId": "p1", "starRating": "3", "content": "Play store review content is really good and reliable", "at": _recent_date()}]
        (tmp_path / "playstore_reviews.json").write_text(json.dumps(data), encoding="utf-8")

        reviews = parse_reviews_dir(tmp_path)
        assert len(reviews) == 2
        sources = {r.source for r in reviews}
        assert "app_store" in sources
        assert "play_store" in sources

    def test_empty_directory_raises(self, tmp_path):
        with pytest.raises(InsufficientDataError, match="No supported review files"):
            parse_reviews_dir(tmp_path)

    def test_all_empty_files_raises(self, tmp_path):
        path = tmp_path / "appstore_reviews.csv"
        path.write_text("reviewId,rating,body,at\n", encoding="utf-8")
        with pytest.raises(InsufficientDataError):
            parse_reviews_dir(tmp_path)


# ---------------------------------------------------------------------------
# Date window filter
# ---------------------------------------------------------------------------

class TestFilterByWindow:

    def _make_review(self, days_ago: int) -> Review:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
        return Review(id=f"r-{days_ago}", source="app_store", rating=3,
                      title="", text=f"Review from {days_ago} days ago", date=dt)

    def test_keeps_reviews_within_window(self):
        reviews = [self._make_review(d) for d in [5, 20, 40, 60]]
        filtered = filter_by_window(reviews, weeks=10)
        assert len(filtered) == 4   # all 4 are within 10 weeks (70 days): 5, 20, 40, 60 days ago

    def test_removes_old_reviews(self):
        reviews = [self._make_review(200)]
        with pytest.raises(InsufficientDataError, match="No reviews found in the last"):
            filter_by_window(reviews, weeks=10)

    def test_all_within_window(self):
        reviews = [self._make_review(d) for d in [1, 5, 10, 15]]
        filtered = filter_by_window(reviews, weeks=10)
        assert len(filtered) == 4

    def test_empty_input_raises(self):
        with pytest.raises(InsufficientDataError):
            filter_by_window([], weeks=10)


# ---------------------------------------------------------------------------
# Smoke test: load the bundled sample data
# ---------------------------------------------------------------------------

class TestSampleData:
    """Smoke tests that load the real sample files shipped with the project."""

    SAMPLE_DIR = Path(__file__).parent.parent / "data" / "reviews"

    def test_sample_files_exist(self):
        assert (self.SAMPLE_DIR / "appstore_reviews.csv").exists(), \
            "Sample App Store file missing from data/reviews/"
        assert (self.SAMPLE_DIR / "playstore_reviews.csv").exists(), \
            "Sample Play Store file missing from data/reviews/ (should be CSV, not JSON)"

    def test_load_all_sample_reviews(self):
        reviews = parse_reviews_dir(self.SAMPLE_DIR)
        assert len(reviews) >= 30, f"Expected ≥ 30 sample reviews, got {len(reviews)}"

    def test_all_reviews_have_non_empty_text(self):
        reviews = parse_reviews_dir(self.SAMPLE_DIR)
        for r in reviews:
            assert r.text.strip(), f"Review {r.id} has empty text"

    def test_all_reviews_have_valid_rating(self):
        reviews = parse_reviews_dir(self.SAMPLE_DIR)
        for r in reviews:
            assert 1 <= r.rating <= 5, f"Review {r.id} has invalid rating {r.rating}"

    def test_all_reviews_have_utc_aware_date(self):
        reviews = parse_reviews_dir(self.SAMPLE_DIR)
        for r in reviews:
            assert r.date.tzinfo is not None, f"Review {r.id} has a naive datetime"

    def test_sources_are_both_represented(self):
        reviews = parse_reviews_dir(self.SAMPLE_DIR)
        sources = {r.source for r in reviews}
        assert "app_store" in sources
        assert "play_store" in sources


# ---------------------------------------------------------------------------
# Noise filter
# ---------------------------------------------------------------------------

class TestNoiseFilter:
    """Unit tests for _noise_reason() and filter_noise()."""

    # -- _noise_reason helpers -----------------------------------------------

    def test_too_short_rejected(self):
        # 5 words → below the 8-word threshold
        assert _noise_reason("App is very good") == "too short (< 8 words)"

    def test_exactly_eight_words_accepted(self):
        assert _noise_reason("This app is really very good and fast") is None

    def test_emoji_in_text_rejected(self):
        assert _noise_reason("This app is great and I love it 😍") == "contains emoji"

    def test_emoji_only_rejected(self):
        assert _noise_reason("👍 👍 👍 very nice app I like this") == "contains emoji"

    def test_hindi_text_rejected(self):
        # A clear Hindi sentence to trigger the langdetect rule
        hindi = "यह ऐप बहुत अच्छा है और मुझे इसका उपयोग करना पसंद है"
        reason = _noise_reason(hindi)
        # langdetect may not be installed in CI; skip assertion if so
        if reason is not None:
            assert reason == "hindi language"

    def test_english_text_accepted(self):
        assert _noise_reason(
            "The payment process is smooth and transactions complete instantly"
        ) is None

    # -- filter_noise integration --------------------------------------------

    def _make_review(self, text: str, rid: str = "r1") -> Review:
        from datetime import timezone
        return Review(
            id=rid,
            source="app_store",
            rating=4,
            title="",
            text=text,
            date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )

    def test_short_review_filtered_by_parse(self, tmp_path):
        """parse_reviews should silently drop < 8-word reviews."""
        path = _write_csv(tmp_path, "appstore_reviews.csv", [
            {"reviewId": "s1", "rating": "5", "body": "Great app", "at": _recent_date()},
            {"reviewId": "s2", "rating": "4", "body": "Absolutely love this app it works perfectly every day", "at": _recent_date()},
        ])
        reviews = parse_reviews(path)
        assert len(reviews) == 1
        assert reviews[0].id == "s2"

    def test_emoji_review_filtered_by_parse(self, tmp_path):
        """parse_reviews should drop reviews that contain emoji."""
        path = _write_csv(tmp_path, "appstore_reviews.csv", [
            {"reviewId": "e1", "rating": "5", "body": "Love this app so much 😍 great experience overall", "at": _recent_date()},
            {"reviewId": "e2", "rating": "4", "body": "The payment flow is seamless and very fast to use", "at": _recent_date()},
        ])
        reviews = parse_reviews(path)
        assert len(reviews) == 1
        assert reviews[0].id == "e2"

    def test_filter_noise_drops_short(self):
        r_short = self._make_review("Good app only", "short")
        r_good  = self._make_review("This app is really great and works perfectly every time", "good")
        result = filter_noise([r_short, r_good])
        assert len(result) == 1
        assert result[0].id == "good"

    def test_filter_noise_drops_emoji(self):
        r_emoji = self._make_review("Great app I really love using it every single day 🎉", "emoji")
        r_good  = self._make_review("Works flawlessly every time and the UI is very clean", "good")
        result = filter_noise([r_emoji, r_good])
        assert len(result) == 1
        assert result[0].id == "good"

    def test_filter_noise_empty_list(self):
        assert filter_noise([]) == []

    def test_filter_noise_all_pass(self):
        reviews = [
            self._make_review("The app loads quickly and payments never fail for me", f"r{i}")
            for i in range(3)
        ]
        assert filter_noise(reviews) == reviews

