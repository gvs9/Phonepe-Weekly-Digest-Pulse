"""
ingestion/parser.py
-------------------
Loads, validates, normalises, and deduplicates raw review exports.

Supported formats: CSV (.csv), JSON (.json), TSV (.tsv / .txt)

App Store column aliases  → canonical name
  reviewId / id           → id
  (implicit app_store)    → source
  rating / score / stars  → rating
  title / reviewTitle     → title
  body / review / content / text → text
  at / date / reviewDate / createdDate → date

Play Store column aliases → canonical name
  reviewId / id           → id
  (implicit play_store)   → source
  starRating / rating     → rating
  reviewCreatedVersion    (ignored)
  content / review / text → text
  at / date               → date
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd
from dateutil import parser as dateutil_parser

from ingestion import InsufficientDataError, Review, SchemaError, Source

# ---------------------------------------------------------------------------
# Noise-filter constants
# ---------------------------------------------------------------------------

# Unicode ranges that cover emoji blocks
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # misc symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"  # alchemical
    "\U0001F780-\U0001F7FF"  # geometric shapes extended
    "\U0001F800-\U0001F8FF"  # supplemental arrows-C
    "\U0001F900-\U0001F9FF"  # supplemental symbols & pictographs
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols & pictographs extended-A
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed characters
    "]+",
    flags=re.UNICODE,
)

_MIN_WORDS = 8  # reviews with fewer words are discarded

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column alias maps  (alias → canonical)
# ---------------------------------------------------------------------------

_ID_ALIASES = {"reviewid", "id", "review_id"}
_RATING_ALIASES = {"rating", "score", "stars", "starrating"}
_TITLE_ALIASES = {"title", "reviewtitle", "review_title"}
_TEXT_ALIASES = {"body", "review", "content", "text", "reviewbody"}
_DATE_ALIASES = {"at", "date", "reviewdate", "createdat", "createddate", "reviewcreatedversion"}

# Source is determined by the filename keyword or an explicit `source` column
_SOURCE_FILENAME_MAP = {
    "appstore": "app_store",
    "app_store": "app_store",
    "apple": "app_store",
    "ios": "app_store",
    "playstore": "play_store",
    "play_store": "play_store",
    "android": "play_store",
    "google": "play_store",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_source_from_filename(filepath: Path) -> Source:
    stem = filepath.stem.lower().replace("-", "_").replace(" ", "_")
    for keyword, source in _SOURCE_FILENAME_MAP.items():
        if keyword in stem:
            return source  # type: ignore[return-value]
    logger.warning(
        "Could not determine source from filename '%s'. Defaulting to 'unknown'.",
        filepath.name,
    )
    return "unknown"


def _normalise_columns(df: pd.DataFrame) -> dict[str, str]:
    """
    Return a mapping {canonical_name: actual_col} for the columns we care about.
    Raises SchemaError if required columns (text, date) are missing.
    """
    lower_cols = {col.lower().replace(" ", "").replace("_", ""): col for col in df.columns}

    def find(aliases: set[str]) -> Optional[str]:
        for alias in aliases:
            key = alias.replace("_", "")
            if key in lower_cols:
                return lower_cols[key]
        return None

    mapping: dict[str, str] = {}

    if col := find(_TEXT_ALIASES):
        mapping["text"] = col
    if col := find(_DATE_ALIASES):
        mapping["date"] = col
    if col := find(_RATING_ALIASES):
        mapping["rating"] = col
    if col := find(_TITLE_ALIASES):
        mapping["title"] = col
    if col := find(_ID_ALIASES):
        mapping["id"] = col

    # Required columns
    missing = [name for name in ("text", "date") if name not in mapping]
    if missing:
        raise SchemaError(
            f"Missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    return mapping


def _parse_date_safe(raw: object, review_id: str) -> Optional[datetime]:
    """Parse a date value into a UTC-aware datetime; return None on failure."""
    if pd.isna(raw) or str(raw).strip() in ("", "N/A", "null", "None"):
        logger.warning("Skipped review %s: missing/empty date.", review_id)
        return None
    try:
        dt = dateutil_parser.parse(str(raw))
        # Ensure UTC-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except (ValueError, OverflowError) as exc:
        logger.warning("Skipped review %s: invalid date '%s' (%s).", review_id, raw, exc)
        return None


def _parse_rating_safe(raw: object, review_id: str) -> Optional[int]:
    """Parse a rating value to int 1–5; return None on failure."""
    try:
        rating = int(float(str(raw)))
        if 1 <= rating <= 5:
            return rating
        logger.warning("Skipped review %s: rating %s out of range 1–5.", review_id, rating)
        return None
    except (ValueError, TypeError):
        logger.warning("Skipped review %s: unparseable rating '%s'.", review_id, raw)
        return None


def _load_raw(filepath: Path) -> pd.DataFrame:
    """Load a file into a DataFrame based on its extension."""
    ext = filepath.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(filepath, dtype=str, keep_default_na=False)
    elif ext in (".tsv", ".txt"):
        return pd.read_csv(filepath, sep="\t", dtype=str, keep_default_na=False)
    elif ext == ".json":
        return pd.read_json(filepath, dtype=str)
    else:
        raise SchemaError(
            f"Unsupported file format '{ext}'. Supported: .csv, .json, .tsv, .txt"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_reviews(filepath: str | Path) -> List[Review]:
    """
    Load, validate, normalise, and deduplicate reviews from a single file.

    Parameters
    ----------
    filepath : str or Path
        Path to a CSV, JSON, or TSV review export.

    Returns
    -------
    List[Review]
        A list of validated, deduplicated Review objects (may be empty).

    Raises
    ------
    SchemaError
        If required columns are missing or the file format is unsupported.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Review file not found: {filepath}")

    logger.info("Loading reviews from '%s'...", filepath.name)
    df = _load_raw(filepath)

    if df.empty:
        logger.warning("File '%s' contains no rows.", filepath.name)
        return []

    col_map = _normalise_columns(df)
    source: Source = _detect_source_from_filename(filepath)

    reviews: List[Review] = []
    seen: set[tuple] = set()
    skipped_empty = 0
    skipped_date = 0
    skipped_rating = 0
    skipped_dup = 0
    skipped_noise = 0  # short / emoji / hindi

    for _, row in df.iterrows():
        # --- text ---
        text = str(row.get(col_map["text"], "")).strip()
        if not text:
            skipped_empty += 1
            continue

        # --- noise filter (< 8 words / emoji / Hindi) ---
        noise_reason = _noise_reason(text)
        if noise_reason:
            skipped_noise += 1
            logger.debug("Skipped review (noise – %s): %.60r", noise_reason, text)
            continue

        # --- id (generate if missing) ---
        raw_id = str(row.get(col_map.get("id", ""), "")).strip()
        review_id = raw_id if raw_id else str(uuid.uuid4())

        # --- date ---
        date = _parse_date_safe(row.get(col_map["date"]), review_id)
        if date is None:
            skipped_date += 1
            continue

        # --- rating ---
        rating_raw = row.get(col_map.get("rating", ""), 3)
        rating = _parse_rating_safe(rating_raw, review_id)
        if rating is None:
            skipped_rating += 1
            continue

        # --- title ---
        title = str(row.get(col_map.get("title", ""), "")).strip()

        # --- source override from column ---
        if "source" in df.columns:
            raw_source = str(row.get("source", "")).strip().lower()
            if raw_source in ("app_store", "play_store"):
                source = raw_source  # type: ignore[assignment]

        # --- deduplication key ---
        dup_key = (source, review_id) if raw_id else (source, text[:100], str(date.date()))
        if dup_key in seen:
            skipped_dup += 1
            continue
        seen.add(dup_key)

        reviews.append(
            Review(
                id=review_id,
                source=source,
                rating=rating,
                title=title,
                text=text,
                date=date,
            )
        )

    logger.info(
        "Parsed %d reviews from '%s'. Skipped: %d empty text, %d bad date, "
        "%d bad rating, %d duplicates, %d noise (short/emoji/hindi).",
        len(reviews),
        filepath.name,
        skipped_empty,
        skipped_date,
        skipped_rating,
        skipped_dup,
        skipped_noise,
    )
    return reviews


def parse_reviews_dir(directory: str | Path) -> List[Review]:
    """
    Load reviews from all supported files in a directory.

    Parameters
    ----------
    directory : str or Path
        Directory containing review export files.

    Returns
    -------
    List[Review]
        Combined, globally deduplicated list of reviews from all files.

    Raises
    ------
    InsufficientDataError
        If the directory contains no supported files or all files are empty.
    """
    directory = Path(directory)
    supported = list(directory.glob("*.csv")) + \
                list(directory.glob("*.json")) + \
                list(directory.glob("*.tsv")) + \
                list(directory.glob("*.txt"))

    if not supported:
        raise InsufficientDataError(
            f"No supported review files found in '{directory}'. "
            "Place CSV, JSON, or TSV exports there."
        )

    all_reviews: List[Review] = []
    global_seen: set[tuple] = set()

    for filepath in sorted(supported):
        file_reviews = parse_reviews(filepath)
        for review in file_reviews:
            key = (review.source, review.id)
            if key not in global_seen:
                global_seen.add(key)
                all_reviews.append(review)

    if not all_reviews:
        raise InsufficientDataError(
            "All review files were empty or contained only invalid rows."
        )

    return all_reviews


# ---------------------------------------------------------------------------
# Internal noise-filter helper
# ---------------------------------------------------------------------------

def _noise_reason(text: str) -> Optional[str]:
    """
    Return a short string describing why *text* is considered noise,
    or ``None`` if the review is acceptable.

    A review is noise if it:
    * has fewer than 8 words,
    * contains any emoji character, or
    * is detected as Hindi (``langdetect`` language code ``"hi"``)
      with probability ≥ 0.80.
    """
    # 1. Word-count check
    if len(text.split()) < _MIN_WORDS:
        return "too short (< 8 words)"

    # 2. Emoji check
    if _EMOJI_RE.search(text):
        return "contains emoji"

    # 3. Hindi language check
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0          # make detection deterministic
        langs = detect_langs(text)
        if langs and langs[0].lang == "hi" and langs[0].prob >= 0.80:
            return "hindi language"
    except Exception:
        # langdetect not installed or detection failed → do not discard
        pass

    return None


def filter_by_window(reviews: List[Review], weeks: int = 10) -> List[Review]:
    """
    Keep only reviews submitted within the last `weeks` weeks from today (UTC).

    Parameters
    ----------
    reviews : List[Review]
    weeks : int
        Number of weeks to look back (default 10, range 8–12).

    Returns
    -------
    List[Review]

    Raises
    ------
    InsufficientDataError
        If no reviews fall within the window.
    """
    from datetime import timedelta

    cutoff = datetime.now(tz=timezone.utc) - timedelta(weeks=weeks)
    filtered = [r for r in reviews if r.date >= cutoff]

    if not filtered:
        raise InsufficientDataError(
            f"No reviews found in the last {weeks} weeks "
            f"(cutoff: {cutoff.strftime('%Y-%m-%d')}). "
            "Try increasing review_window_weeks in config.yaml."
        )

    logger.info(
        "Date filter: kept %d / %d reviews (last %d weeks, cutoff %s).",
        len(filtered),
        len(reviews),
        weeks,
        cutoff.strftime("%Y-%m-%d"),
    )
    return filtered


def filter_noise(reviews: List[Review]) -> List[Review]:
    """
    Remove noisy reviews from an already-parsed list.

    A review is considered noise if it:
    * has fewer than 8 words,
    * contains any emoji character, or
    * is detected as Hindi (langdetect code ``"hi"``) with probability ≥ 0.80.

    This function is the post-parse counterpart to the inline check in
    :func:`parse_reviews`. Use it when working with :class:`Review` objects
    that were not loaded through the parser (e.g. from the scraper).

    Parameters
    ----------
    reviews : List[Review]

    Returns
    -------
    List[Review]
        Reviews that passed all noise checks.
    """
    kept: List[Review] = []
    dropped = 0
    for review in reviews:
        reason = _noise_reason(review.text)
        if reason:
            logger.debug("filter_noise: dropped review %s (%s).", review.id, reason)
            dropped += 1
        else:
            kept.append(review)

    logger.info(
        "filter_noise: kept %d / %d reviews (%d dropped).",
        len(kept), len(reviews), dropped,
    )
    return kept
