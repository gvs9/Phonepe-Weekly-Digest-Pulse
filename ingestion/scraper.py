"""
ingestion/scraper.py
--------------------
Fetches real reviews directly from the App Store and Play Store
using public scraper libraries (no API keys required).

Libraries used:
    google-play-scraper  -- https://pypi.org/project/google-play-scraper/
    app-store-scraper    -- https://pypi.org/project/app-store-scraper/

Usage
-----
    from ingestion.scraper import fetch_all_reviews, save_reviews_to_csv

    reviews = fetch_all_reviews(
        play_store_id="com.phonepe.app",
        app_store_id="1170592612",
        app_name="PhonePe",
        country="in",
        weeks=12,
    )
    save_reviews_to_csv(reviews, "data/reviews/")

Config-driven (used by main.py)
---------------------------------
Add to config.yaml:

    app:
      name: "MyApp"
      play_store_id: "com.example.app"
      app_store_id: "123456789"
      country: "in"
"""

from __future__ import annotations

import csv
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal normalisation helpers
# ---------------------------------------------------------------------------

def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is UTC-aware; return None if input is None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _cutoff(weeks: int) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(weeks=weeks)


# ---------------------------------------------------------------------------
# Play Store scraper
# ---------------------------------------------------------------------------

def fetch_play_store_reviews(
    package_name: str,
    weeks: int = 12,
    country: str = "in",
    lang: str = "en",
    max_reviews: int = 500,
) -> List[dict]:
    """
    Fetch reviews from the Google Play Store.

    Parameters
    ----------
    package_name : str
        e.g. "com.phonepe.app"
    weeks : int
        Only keep reviews newer than this many weeks.
    country : str
        Two-letter country code (default "in" for India).
    lang : str
        Language code (default "en").
    max_reviews : int
        Maximum number of reviews to attempt to fetch.

    Returns
    -------
    List[dict]
        List of normalised review dicts with canonical field names.
    """
    try:
        from google_play_scraper import Sort, reviews as gps_reviews
    except ImportError:
        raise ImportError(
            "google-play-scraper is not installed. "
            "Run: pip install google-play-scraper"
        )

    cut = _cutoff(weeks)
    logger.info(
        "Fetching Play Store reviews for '%s' (country=%s, cutoff=%s)...",
        package_name, country, cut.strftime("%Y-%m-%d"),
    )

    results: List[dict] = []
    continuation_token = None
    batch_size = 100
    total_fetched = 0

    while total_fetched < max_reviews:
        fetch_count = min(batch_size, max_reviews - total_fetched)
        try:
            batch, continuation_token = gps_reviews(
                package_name,
                lang=lang,
                country=country,
                sort=Sort.NEWEST,
                count=fetch_count,
                continuation_token=continuation_token,
            )
        except Exception as exc:
            logger.warning("Play Store fetch error: %s. Stopping early.", exc)
            break

        if not batch:
            break

        stopped_early = False
        for item in batch:
            at: Optional[datetime] = _to_utc(item.get("at"))
            if at is None or at < cut:
                stopped_early = True
                break

            text = str(item.get("content") or "").strip()
            if not text:
                continue

            results.append({
                "id":     str(item.get("reviewId") or ""),
                "source": "play_store",
                "rating": int(item.get("score") or 3),
                "title":  str(item.get("title") or ""),
                "text":   text,
                "date":   at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        total_fetched += len(batch)

        if stopped_early or continuation_token is None:
            break

        time.sleep(0.5)   # be polite to the API

    logger.info("Play Store: fetched %d reviews within the last %d weeks.", len(results), weeks)
    return results


# ---------------------------------------------------------------------------
# App Store scraper
# ---------------------------------------------------------------------------

def fetch_app_store_reviews(
    app_id: str,
    app_name: str,
    weeks: int = 12,
    country: str = "in",
    max_reviews: int = 500,
) -> List[dict]:
    """
    Fetch reviews from the Apple App Store via the public iTunes RSS API.

    Uses Apple's official RSS feed endpoint — no library, no credentials needed:
    https://itunes.apple.com/{country}/rss/customerreviews/page={n}/id={app_id}/sortby=mostrecent/json

    Parameters
    ----------
    app_id : str
        Numeric App Store app ID (e.g. "1170592612"). No "id" prefix.
    app_name : str
        Human-readable name (used only for logging).
    weeks : int
        Only keep reviews newer than this many weeks.
    country : str
        Two-letter country code (default "in").
    max_reviews : int
        Maximum number of reviews to fetch (Apple caps at 500 = 10 pages × 50).

    Returns
    -------
    List[dict]
        List of normalised review dicts with canonical field names.
    """
    import json as _json
    try:
        import requests as _requests
    except ImportError:
        raise ImportError("requests is not installed. Run: pip install requests")

    cut = _cutoff(weeks)
    logger.info(
        "Fetching App Store reviews for '%s' (id=%s, country=%s, cutoff=%s) via iTunes RSS...",
        app_name, app_id, country, cut.strftime("%Y-%m-%d"),
    )

    results: List[dict] = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    for page in range(1, 11):   # Apple RSS gives max 10 pages of 50 = 500 reviews
        if len(results) >= max_reviews:
            break

        url = (
            f"https://itunes.apple.com/{country}/rss/customerreviews"
            f"/page={page}/id={app_id}/sortby=mostrecent/json"
        )

        try:
            resp = _requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("App Store page %d fetch error: %s", page, exc)
            time.sleep(2)
            continue

        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            logger.info("App Store: no more entries at page %d.", page)
            break

        # First entry on page 1 is app metadata, not a review — skip it
        if page == 1 and entries and "im:rating" not in entries[0]:
            entries = entries[1:]

        stopped_early = False
        for entry in entries:
            # Parse date
            raw_date = entry.get("updated", {}).get("label", "")
            at = _parse_itunes_date(raw_date)
            if at is None:
                continue
            if at < cut:
                stopped_early = True
                break

            text = entry.get("content", {}).get("label", "").strip()
            if not text:
                continue

            review_id = entry.get("id", {}).get("label", "")
            title = entry.get("title", {}).get("label", "")
            rating_raw = entry.get("im:rating", {}).get("label", "3")
            try:
                rating = max(1, min(5, int(rating_raw)))
            except (ValueError, TypeError):
                rating = 3

            results.append({
                "id":     review_id,
                "source": "app_store",
                "rating": rating,
                "title":  title,
                "text":   text,
                "date":   at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        if stopped_early:
            break

        time.sleep(0.5)   # polite delay between pages

    logger.info("App Store: fetched %d reviews within the last %d weeks.", len(results), weeks)
    return results


def _parse_itunes_date(raw: str) -> Optional[datetime]:
    """Parse an iTunes RSS date string to a UTC-aware datetime."""
    if not raw:
        return None
    try:
        from dateutil import parser as _dp
        dt = _dp.parse(raw)
        return _to_utc(dt)
    except Exception:
        return None



# ---------------------------------------------------------------------------
# Save to CSV
# ---------------------------------------------------------------------------

def save_reviews_to_csv(reviews: List[dict], output_dir: str | Path, filename: str) -> Path:
    """
    Write a list of normalised review dicts to a CSV file.

    Parameters
    ----------
    reviews : List[dict]
        Normalised reviews (output of fetch_* functions).
    output_dir : str or Path
        Directory to write the CSV into.
    filename : str
        Output filename (e.g. "playstore_reviews.csv").

    Returns
    -------
    Path
        The path of the written file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename

    fieldnames = ["id", "source", "rating", "title", "text", "date"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in reviews:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    logger.info("Saved %d reviews to '%s'.", len(reviews), path)
    return path


# ---------------------------------------------------------------------------
# Convenience: fetch both stores + save
# ---------------------------------------------------------------------------

def fetch_all_reviews(
    play_store_id: str,
    app_store_id: str,
    app_name: str,
    country: str = "in",
    weeks: int = 12,
    max_reviews: int = 500,
    output_dir: str | Path = "data/reviews",
) -> dict[str, Path]:
    """
    Fetch reviews from both stores, save them as CSVs, and return the file paths.

    Parameters
    ----------
    play_store_id : str
        Play Store package name, e.g. "com.phonepe.app"
    app_store_id : str
        App Store numeric ID, e.g. "1170592612"
    app_name : str
        Human-readable app name for the App Store scraper.
    country : str
        Two-letter country code (default "in").
    weeks : int
        Review window in weeks (default 12).
    max_reviews : int
        Max reviews to fetch per store (default 500).
    output_dir : str or Path
        Directory to save CSVs (default "data/reviews").

    Returns
    -------
    dict[str, Path]
        {"play_store": Path, "app_store": Path}
    """
    paths: dict[str, Path] = {}

    # Play Store
    if play_store_id:
        ps_reviews = fetch_play_store_reviews(
            play_store_id, weeks=weeks, country=country, max_reviews=max_reviews
        )
        if ps_reviews:
            paths["play_store"] = save_reviews_to_csv(
                ps_reviews, output_dir, "playstore_reviews.csv"
            )
        else:
            logger.warning("No Play Store reviews fetched for '%s'.", play_store_id)
    else:
        logger.warning("play_store_id not configured — skipping Play Store fetch.")

    # App Store
    if app_store_id:
        as_reviews = fetch_app_store_reviews(
            app_store_id, app_name=app_name, weeks=weeks,
            country=country, max_reviews=max_reviews
        )
        if as_reviews:
            paths["app_store"] = save_reviews_to_csv(
                as_reviews, output_dir, "appstore_reviews.csv"
            )
        else:
            logger.warning("No App Store reviews fetched for '%s'.", app_store_id)
    else:
        logger.warning("app_store_id not configured — skipping App Store fetch.")

    return paths
