"""
main.py
-------
Pipeline entry point for the Mobile-Store Feedback system.

Usage
-----
    python main.py              # run full pipeline (all phases)
    python main.py --phase 1    # run up to (and including) phase N
    python main.py --dry-run    # skip all external API calls
    python main.py --init       # create a default config.yaml

Phases
------
    1  Foundation & Data Ingestion
    2  Thematic Grouping
    3  Pulse Generator
    4  Groq LLM Polish
    5  Google Docs Integration
    6  Gmail Integration & Orchestration
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from ingestion import ConfigError, InsufficientDataError, SchemaError
from ingestion.parser import filter_by_window, parse_reviews_dir
from themes import ThemeConfig
from themes.clusterer import assign_themes, rank_themes
from llm.groq_client import enrich_with_llm
from pulse.generator import build_pulse
import os

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).parent / "config.yaml"
DATA_DIR    = Path(__file__).parent / "data" / "reviews"

# Load .env before anything else
load_dotenv(Path(__file__).parent / ".env")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load and return the config.yaml as a dict."""
    if not path.exists():
        raise ConfigError(
            f"config.yaml not found at '{path}'. "
            "Run: python main.py --init  to create a default config."
        )
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if cfg is None:
        raise ConfigError("config.yaml is empty.")
    # .env values take priority over config.yaml
    if os.getenv("APP_NAME"):            cfg.setdefault("app", {})["name"]          = os.getenv("APP_NAME")
    if os.getenv("APP_PLAY_STORE_ID"):   cfg.setdefault("app", {})["play_store_id"] = os.getenv("APP_PLAY_STORE_ID")
    if os.getenv("APP_APP_STORE_ID"):    cfg.setdefault("app", {})["app_store_id"]  = os.getenv("APP_APP_STORE_ID")
    if os.getenv("APP_COUNTRY"):         cfg.setdefault("app", {})["country"]       = os.getenv("APP_COUNTRY")
    if os.getenv("REVIEW_WINDOW_WEEKS"): cfg["review_window_weeks"]                 = int(os.getenv("REVIEW_WINDOW_WEEKS"))
    if os.getenv("GMAIL_RECIPIENT"):     cfg["gmail_recipient"]                      = os.getenv("GMAIL_RECIPIENT")
    if os.getenv("GOOGLE_DOC_ID"):       cfg["google_doc_id"]                        = os.getenv("GOOGLE_DOC_ID")
    if os.getenv("GROQ_MODEL"):          cfg["groq_model"]                           = os.getenv("GROQ_MODEL")
    return cfg


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------

def run_phase_1(config: dict, fetch: bool = False) -> None:
    """
    Phase 1 — Foundation & Data Ingestion.

    If fetch=True, pulls real reviews from App Store and Play Store
    using app IDs from config.yaml and saves them to data/reviews/.
    Then loads all review files, applies the date window filter,
    and prints a summary to stdout.
    """
    print("\n" + "=" * 60)
    print("  PHASE 1 — Data Ingestion")
    print("=" * 60)

    weeks = int(config.get("review_window_weeks", 12))
    app_cfg = config.get("app", {})

    # 1a. Optionally fetch real reviews from stores
    if fetch:
        from ingestion.scraper import fetch_all_reviews
        play_id = app_cfg.get("play_store_id", "").strip()
        as_id   = app_cfg.get("app_store_id", "").strip()
        name    = app_cfg.get("name", "App").strip()
        country = app_cfg.get("country", "in").strip()

        if not play_id and not as_id:
            print("  [!] No app IDs configured in config.yaml under 'app:'.")
            print("      Set play_store_id and/or app_store_id, then re-run with --fetch.")
        else:
            print(f"  Fetching real reviews for '{name}' ...")
            paths = fetch_all_reviews(
                play_store_id=play_id,
                app_store_id=as_id,
                app_name=name,
                country=country,
                weeks=weeks,
                max_reviews=500,
                output_dir=DATA_DIR,
            )
            if paths:
                for store, p in paths.items():
                    print(f"  [OK] {store:<15} -> {p}")
            else:
                print("  [!] No reviews fetched. Check your app IDs and internet connection.")
        print()

    # 1b. Load all review files from data/reviews/
    all_reviews = parse_reviews_dir(DATA_DIR)

    # 2. Apply date window
    filtered = filter_by_window(all_reviews, weeks=weeks)

    # 3. Summary
    dates = [r.date for r in filtered]
    earliest = min(dates).strftime("%Y-%m-%d")
    latest = max(dates).strftime("%Y-%m-%d")

    source_counts: dict[str, int] = {}
    for r in filtered:
        source_counts[r.source] = source_counts.get(r.source, 0) + 1

    rating_dist: dict[int, int] = {}
    for r in filtered:
        rating_dist[r.rating] = rating_dist.get(r.rating, 0) + 1
    avg_rating = sum(r.rating for r in filtered) / len(filtered)

    print(f"\n  [OK] Reviews loaded    : {len(all_reviews)}")
    print(f"  [OK] After date filter : {len(filtered)}  (last {weeks} weeks)")
    print(f"  [OK] Date range        : {earliest}  ->  {latest}")
    print(f"  [OK] Average rating    : {avg_rating:.2f} / 5.00")
    print()
    print("  Source breakdown:")
    for source, count in sorted(source_counts.items()):
        pct = count / len(filtered) * 100
        print(f"    - {source:<15} {count:>4} reviews  ({pct:.0f}%)")
    print()
    print("  Rating distribution:")
    for stars in range(5, 0, -1):
        count = rating_dist.get(stars, 0)
        bar = "|" * count
        print(f"    {'*' * stars:<5}  {count:>3}  {bar}")
    print()
    print("  Phase 1 complete.\n")
    return filtered   # pass to next phase


def run_phase_2(config: dict, reviews: list) -> tuple[list, object]:
    """
    Phase 2 — Thematic Grouping.

    Assigns each review to the first keyword-matching theme defined in
    config.yaml, ranks themes by volume, and prints the summary table.

    Parameters
    ----------
    config : dict
        Parsed config.yaml.
    reviews : list[Review]
        Date-filtered reviews from Phase 1.

    Returns
    -------
    list[Theme]
        Named themes sorted descending by review count (for Phase 3).
    """
    from datetime import date
    print("\n" + "=" * 60)
    print("  PHASE 2 — Thematic Grouping")
    print("=" * 60)

    theme_config = ThemeConfig.from_config(config)
    all_themes = assign_themes(reviews, theme_config)
    ranked = rank_themes(all_themes)

    other = next((t for t in all_themes if t.name == "other"), None)
    total = len(reviews)
    week_ending = date.today().strftime("%Y-%m-%d")

    print(f"\n  Theme Results (week ending {week_ending})")
    print("  " + "-" * 44)
    for theme in ranked:
        pct = theme.count / total * 100 if total else 0
        print(f"  {theme.name:<15} {theme.count:>4} reviews  ({pct:.0f}%)")
    if other:
        pct = other.count / total * 100 if total else 0
        print(f"  {'[other]':<15} {other.count:>4} reviews  (not included in pulse)")
    print()

    print("  Phase 2 complete.\n")
    return ranked, other


def run_phase_4(pulse: object, config: dict, dry_run: bool = False) -> object:
    """
    Phase 4 — Groq LLM Polish.

    Enriches the Phase 3 PulseNote with Groq-polished action ideas and
    email metadata (subject + intro). Falls back to Phase 3 output on any
    failure or when ``--dry-run`` is active.

    Parameters
    ----------
    pulse : PulseNote
        Output of Phase 3.
    config : dict
        Parsed config.yaml (reads ``groq_model``).
    dry_run : bool
        If True, skip the Groq call entirely.

    Returns
    -------
    PulseNote
        Enriched (or original fallback) PulseNote.
    """
    print("\n" + "=" * 60)
    print("  PHASE 4 — Groq LLM Polish")
    print("=" * 60)

    if dry_run:
        print("  [DRY-RUN] Skipping Groq call — using Phase 3 rule-based output.")
        enriched = enrich_with_llm(pulse, config, dry_run=True)
    else:
        print(f"  Calling Groq API (model: {config.get('groq_model', 'llama3-8b-8192')}) ...")
        enriched = enrich_with_llm(pulse, config, dry_run=False)

    print()
    print("  Polished Actions:")
    for i, action in enumerate(enriched.actions, 1):
        print(f"    {i}. {action}")
    print()
    print(f"  Email subject : {enriched.email_subject}")
    print(f"  Email intro   : {enriched.email_intro[:80]}{'...' if len(enriched.email_intro) > 80 else ''}")
    print()
    print("  Phase 4 complete.\n")
    return enriched


def run_phase_5(pulse: object, config: dict, dry_run: bool = False) -> Optional[str]:
    print("\n" + "=" * 60)
    print("  PHASE 5 — Google Docs via MCP Server")
    print("=" * 60)
    
    if dry_run:
        print("  [DRY-RUN] Skipping Google Docs publishing via MCP.")
        print("  Phase 5 complete.\n")
        return None
        
    try:
        from integrations.mcp_client import publish_to_google_doc
        print("  Connecting to MCP Server and appending to Google Doc...")
        doc_url = publish_to_google_doc(pulse, config)
        if doc_url:
            print(f"  Success! Google Doc URL: {doc_url}")
        else:
            print("  Publishing failed or was skipped (check logs).")
    except ImportError:
        print("  'mcp' SDK not installed. Skipping Phase 5.")
        doc_url = None
        
    print("\n  Phase 5 complete.\n")
    return doc_url


def run_phase_6(pulse: object, doc_url: Optional[str], config: dict, dry_run: bool = False) -> Optional[str]:
    print("\n" + "=" * 60)
    print("  PHASE 6 — Gmail Draft via MCP Server")
    print("=" * 60)
    
    if dry_run:
        print("  [DRY-RUN] Skipping Gmail draft creation via MCP.")
        print("  Phase 6 complete.\n")
        return None
        
    try:
        from integrations.mcp_client import create_gmail_draft_mcp
        print("  Connecting to MCP Server and creating Gmail draft...")
        draft_result = create_gmail_draft_mcp(pulse, doc_url, config)
        if draft_result:
            print(f"  Success! {draft_result}")
        else:
            print("  Draft creation failed or was skipped (check logs).")
    except ImportError:
        print("  'mcp' SDK not installed. Skipping Phase 6.")
        draft_result = None
        
    print("\n  Phase 6 complete.\n")
    return draft_result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mobile-Store Feedback pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--phase",
        type=int,
        default=6,
        choices=range(1, 7),
        metavar="N",
        help="Run up to and including phase N (1–6). Default: 6 (full pipeline).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip all external API calls (Groq, Google Docs, Gmail).",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Print setup instructions and exit.",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch real reviews from App Store and Play Store before running the pipeline.",
    )
    return parser.parse_args()


def check_python_version() -> None:
    if sys.version_info < (3, 10):
        print(
            f"ERROR: Python 3.10+ required. Current: {sys.version.split()[0]}",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    check_python_version()
    args = parse_args()

    if args.init:
        print(__doc__)
        sys.exit(0)

    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    dry_run = args.dry_run
    if dry_run:
        print("\n  [DRY-RUN MODE — no external APIs will be called]\n")

    doc_url = None
    draft_id = None

    try:
        if args.phase >= 1:
            filtered = run_phase_1(config, fetch=args.fetch)

        if args.phase >= 2:
            ranked_themes, other_bucket = run_phase_2(config, filtered)

        if args.phase >= 3:
            print("\n" + "=" * 60)
            print("  PHASE 3 — Pulse Generator")
            print("=" * 60)
            # Build pulse
            pulse = build_pulse(ranked_themes, other_bucket)
            # Save to disk
            os.makedirs("data", exist_ok=True)
            pulse_path = f"data/pulse_{pulse.week_ending}.md"
            with open(pulse_path, "w", encoding="utf-8") as f:
                f.write(pulse.as_markdown())
            print(f"  Pulse generated and saved to {pulse_path}")
            print("  Phase 3 complete.\n")

        if args.phase >= 4:
            # Phase 4 updates the PulseNote with Groq LLM Polish
            pulse = run_phase_4(pulse, config, dry_run=args.dry_run)
            # Save the enriched pulse to disk
            pulse_path = f"data/pulse_{pulse.week_ending}_enriched.md"
            with open(pulse_path, "w", encoding="utf-8") as f:
                f.write(pulse.as_markdown())
            print(f"  Enriched pulse saved to {pulse_path}")

        if args.phase >= 5:
            doc_url = run_phase_5(pulse, config, dry_run=args.dry_run)

        if args.phase >= 6:
            draft_id = run_phase_6(pulse, doc_url, config, dry_run=args.dry_run)
            
            print("\n" + "=" * 60)
            print("  FINAL SUMMARY")
            print("=" * 60)
            num_filtered = len(filtered) if 'filtered' in locals() else 'N/A'
            num_themes = len(ranked_themes) if 'ranked_themes' in locals() else 'N/A'
            print(f"  [OK] Reviews loaded:    {num_filtered}")
            print(f"  [OK] Themes identified: {num_themes}")
            if 'pulse_path' in locals():
                print(f"  [OK] Pulse generated:   {pulse_path}")
            print(f"  [OK] Groq LLM:          report + email body generated")
            if doc_url:
                print(f"  [OK] Google Doc:        {doc_url}")
            if draft_id:
                print(f"  [OK] Gmail draft:       {draft_id}")
            print("=" * 60 + "\n")

    except InsufficientDataError as exc:
        logger.error("Insufficient data: %s", exc)
        sys.exit(1)
    except SchemaError as exc:
        logger.error("Schema error: %s", exc)
        sys.exit(1)
    except ConfigError as exc:
        logger.error("Config error: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
