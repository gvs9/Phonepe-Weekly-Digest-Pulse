"""
generate_output.py
------------------
Runs the full analysis pipeline (Phases 1-3) and writes four
structured JSON artifacts into the output/ folder:

    output/normalised_reviews.json  — every review post-ingestion & date-filter
    output/analyzed_themes.json     — theme assignment + ranked buckets
    output/pulse_draft.json         — raw pulse (quotes, actions, emerging issue)
    output/rendered_artifacts.json  — final human-readable rendered surfaces

Usage:
    python generate_output.py
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import os

import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
load_dotenv(ROOT if 'ROOT' in dir() else Path(__file__).parent / '.env')

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("generate_output")

ROOT      = Path(__file__).parent
load_dotenv(ROOT / '.env')   # load early so os.getenv works below
OUTPUT    = ROOT / "output"
DATA_DIR  = ROOT / "data" / "reviews"
CFG_PATH  = ROOT / "config.yaml"
OUTPUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# 0. Load config
# ---------------------------------------------------------------------------
with open(CFG_PATH, encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

# .env values override config.yaml for product identity & window
if os.getenv("APP_NAME"):              CONFIG.setdefault("app", {})["name"]           = os.getenv("APP_NAME")
if os.getenv("APP_PLAY_STORE_ID"):     CONFIG.setdefault("app", {})["play_store_id"]  = os.getenv("APP_PLAY_STORE_ID")
if os.getenv("APP_APP_STORE_ID"):      CONFIG.setdefault("app", {})["app_store_id"]   = os.getenv("APP_APP_STORE_ID")
if os.getenv("APP_COUNTRY"):           CONFIG.setdefault("app", {})["country"]        = os.getenv("APP_COUNTRY")
if os.getenv("REVIEW_WINDOW_WEEKS"):   CONFIG["review_window_weeks"]                  = int(os.getenv("REVIEW_WINDOW_WEEKS"))
if os.getenv("GMAIL_RECIPIENT"):       CONFIG["gmail_recipient"]                       = os.getenv("GMAIL_RECIPIENT")
if os.getenv("GOOGLE_DOC_ID"):         CONFIG["google_doc_id"]                         = os.getenv("GOOGLE_DOC_ID")
if os.getenv("GROQ_MODEL"):            CONFIG["groq_model"]                            = os.getenv("GROQ_MODEL")

WEEKS        = int(CONFIG.get("review_window_weeks", 12))
THEME_DEFS   = CONFIG.get("themes", [])
MIN_REVIEWS  = int(CONFIG.get("min_reviews_per_theme", 3))
QUOTE_MINLEN = int(CONFIG.get("quote_min_length", 30))

log.info("App : %s  |  Play: %s  |  AppStore: %s  |  Window: %d weeks  |  Groq: %s",
         CONFIG.get('app', {}).get('name', '?'),
         CONFIG.get('app', {}).get('play_store_id', '?'),
         CONFIG.get('app', {}).get('app_store_id', '?'),
         WEEKS,
         CONFIG.get('groq_model', '?'))

# ---------------------------------------------------------------------------
# 1. Ingest & normalise
# ---------------------------------------------------------------------------
log.info("=== Phase 1: Ingestion ===")
from ingestion.parser import filter_by_window, parse_reviews_dir
from ingestion       import Review

all_reviews = parse_reviews_dir(DATA_DIR)
reviews     = filter_by_window(all_reviews, weeks=WEEKS)
log.info("Loaded %d reviews (after filter)", len(reviews))

# Serialise each Review to a plain dict
def review_to_dict(r: Review) -> dict:
    return {
        "id":     r.id,
        "source": r.source,
        "rating": r.rating,
        "title":  r.title,
        "text":   r.text,
        "date":   r.date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stars":  r.stars,
    }

normalised_payload = {
    "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "review_window_weeks": WEEKS,
    "total_reviews": len(reviews),
    "date_range": {
        "earliest": min(r.date for r in reviews).strftime("%Y-%m-%d"),
        "latest":   max(r.date for r in reviews).strftime("%Y-%m-%d"),
    },
    "source_breakdown": {
        src: sum(1 for r in reviews if r.source == src)
        for src in sorted({r.source for r in reviews})
    },
    "rating_distribution": {
        str(s): sum(1 for r in reviews if r.rating == s)
        for s in range(1, 6)
    },
    "average_rating": round(sum(r.rating for r in reviews) / len(reviews), 2),
    "reviews": [review_to_dict(r) for r in reviews],
}

(OUTPUT / "normalised_reviews.json").write_text(
    json.dumps(normalised_payload, indent=2, ensure_ascii=False), encoding="utf-8"
)
log.info("Written: output/normalised_reviews.json")

# ---------------------------------------------------------------------------
# 2. Thematic grouping
# ---------------------------------------------------------------------------
log.info("=== Phase 2: Thematic Grouping ===")

if len(THEME_DEFS) > 5:
    raise ValueError(f"Too many themes: {len(THEME_DEFS)} defined, maximum is 5.")

def assign_theme(review: Review, theme_defs: list[dict]) -> str:
    """Return the first matching theme name, or 'other'."""
    haystack = review.searchable_text()
    for td in theme_defs:
        for kw in td.get("keywords", []):
            if kw.lower() in haystack:
                return td["name"]
    return "other"

buckets: dict[str, list[Review]] = {td["name"]: [] for td in THEME_DEFS}
buckets["other"] = []

for r in reviews:
    theme = assign_theme(r, THEME_DEFS)
    r.theme = theme
    buckets[theme].append(r)

# Warn on zero-match named themes
for name, bucket in buckets.items():
    if name != "other" and len(bucket) < MIN_REVIEWS:
        log.warning("Theme '%s' has only %d review(s) — below min_reviews_per_theme=%d.",
                    name, len(bucket), MIN_REVIEWS)

# Rank named themes by count descending
ranked_themes = sorted(
    [{"name": n, "count": len(b), "reviews": b} for n, b in buckets.items() if n != "other"],
    key=lambda x: x["count"], reverse=True
)

def theme_stats(name: str, bucket: list[Review]) -> dict:
    total = len(bucket)
    if total == 0:
        return {"name": name, "count": 0, "pct_of_total": 0.0,
                "avg_rating": None, "rating_distribution": {}}
    return {
        "name": name,
        "count": total,
        "pct_of_total": round(total / len(reviews) * 100, 1),
        "avg_rating": round(sum(r.rating for r in bucket) / total, 2),
        "rating_distribution": {
            str(s): sum(1 for r in bucket if r.rating == s)
            for s in range(1, 6)
        },
        "sample_review_ids": [r.id for r in bucket[:3]],
    }

analyzed_themes_payload = {
    "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "total_reviews_analyzed": len(reviews),
    "theme_config_count": len(THEME_DEFS),
    "ranked_themes": [theme_stats(t["name"], buckets[t["name"]]) for t in ranked_themes],
    "other_bucket": theme_stats("other", buckets["other"]),
    "review_assignments": {r.id: r.theme for r in reviews},
}

(OUTPUT / "analyzed_themes.json").write_text(
    json.dumps(analyzed_themes_payload, indent=2, ensure_ascii=False), encoding="utf-8"
)
log.info("Written: output/analyzed_themes.json")

# ---------------------------------------------------------------------------
# 3. Pulse Generator
# ---------------------------------------------------------------------------
log.info("=== Phase 3: Pulse Generator ===")

week_ending = max(r.date for r in reviews).strftime("%Y-%m-%d")
other_bucket: list[Review] = buckets["other"]

# ---- Quote selection (exactly 3) ----
dominant_bucket = buckets[ranked_themes[0]["name"]] if ranked_themes else []

def best_review(pool: list[Review], prefer_low: bool = False,
                prefer_high: bool = False, exclude_ids: set[str] | None = None) -> Optional[Review]:
    """Pick the longest review from pool, with optional rating preference."""
    pool = [r for r in pool if (exclude_ids is None or r.id not in exclude_ids)
            and len(r.text.strip()) >= QUOTE_MINLEN]
    if not pool:
        return None
    if prefer_low:
        pool = sorted(pool, key=lambda r: (r.rating, -len(r.text)))
    elif prefer_high:
        pool = sorted(pool, key=lambda r: (-r.rating, -len(r.text)))
    else:
        pool = sorted(pool, key=lambda r: -len(r.text))
    return pool[0]

selected_ids: set[str] = set()
quotes: list[dict] = []

# Slot 1 — dominant theme, pain (low rating)
q1 = best_review(dominant_bucket, prefer_low=True)
if q1:
    quotes.append({"slot": 1, "role": "pain", "source_theme": ranked_themes[0]["name"],
                   **review_to_dict(q1)})
    selected_ids.add(q1.id)

# Slot 2 — dominant theme, praise (high rating)
q2 = best_review(dominant_bucket, prefer_high=True, exclude_ids=selected_ids)
if q2:
    quotes.append({"slot": 2, "role": "praise", "source_theme": ranked_themes[0]["name"],
                   **review_to_dict(q2)})
    selected_ids.add(q2.id)

# Slot 3 — fallback cascade: next theme → other bucket
q3 = None
for t in ranked_themes[1:]:
    candidate = best_review(buckets[t["name"]], exclude_ids=selected_ids)
    if candidate:
        q3 = {"slot": 3, "role": "fallback", "source_theme": t["name"],
              **review_to_dict(candidate)}
        selected_ids.add(candidate.id)
        break

if q3 is None:
    # Fall back to other bucket longest 1-star
    candidate = best_review(
        [r for r in other_bucket if r.rating == 1], exclude_ids=selected_ids
    ) or best_review(other_bucket, exclude_ids=selected_ids)
    if candidate:
        q3 = {"slot": 3, "role": "emerging", "source_theme": "other",
              **review_to_dict(candidate)}
        selected_ids.add(candidate.id)

if q3:
    quotes.append(q3)

# ---- Action generation (exactly 3) ----
actions: list[dict] = []

theme_cfg_map = {td["name"]: td for td in THEME_DEFS}

def action_for_theme(name: str, count: int, slot: int) -> dict:
    tmpl = theme_cfg_map.get(name, {}).get(
        "action_template",
        f"Investigate {name} issues raised by {count} users."
    )
    return {"slot": slot, "source_theme": name, "action": tmpl}

if ranked_themes:
    actions.append(action_for_theme(ranked_themes[0]["name"], ranked_themes[0]["count"], 1))

second_theme = next((t for t in ranked_themes[1:] if t["count"] > 0), None)
if second_theme:
    actions.append(action_for_theme(second_theme["name"], second_theme["count"], 2))
elif other_bucket:
    actions.append({
        "slot": 2, "source_theme": "other",
        "action": f"Investigate unclassified issues raised by {len(other_bucket)} users "
                  "— consider expanding keyword config to capture recurring topics."
    })

# Action 3: mine other bucket via word frequency
def mine_emerging_topic(pool: list[Review], top_n: int = 5) -> str:
    STOPWORDS = {
        "the","a","an","and","or","but","in","on","at","to","for","of","with",
        "is","it","i","my","me","we","be","have","this","that","are","was",
        "not","app","phonepe","phone","pe","please","very","has","from","its",
        "all","so","as","can","do","no","they","you","your","our","their","use",
        "using","used","also","still","even","been","had","just","then","now",
        "will","which","when","there","one","more","after","would","could","get",
    }
    texts = [r.text for r in sorted(pool, key=lambda r: (r.rating, -len(r.text)))[:20]]
    words = re.findall(r"[a-z]+", " ".join(texts).lower())
    freq = Counter(w for w in words if w not in STOPWORDS and len(w) > 3)
    top = [w for w, _ in freq.most_common(top_n)]
    return ", ".join(top) if top else "unclassified user issues"

emerging_keywords = mine_emerging_topic(other_bucket) if other_bucket else ""
actions.append({
    "slot": 3,
    "source_theme": "other",
    "action": (
        f"Investigate the top unclassified complaints ({len(other_bucket)} reviews). "
        f"Recurring signals: {emerging_keywords}. "
        "Consider adding a new theme or expanding existing keywords."
    ) if emerging_keywords else
        f"Investigate {len(other_bucket)} unclassified reviews and expand theme keywords."
})

# ---- Emerging issue ----
emerging_issue: Optional[str] = None
if other_bucket:
    emerging_issue = (
        f"{len(other_bucket)} reviews did not match any named theme. "
        f"Top signals from unmatched reviews: {emerging_keywords}. "
        "Consider adding a dedicated theme or expanding existing keyword sets."
    )

pulse_draft_payload = {
    "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "week_ending": week_ending,
    "total_reviews_in_window": len(reviews),
    "top_themes": [
        {"name": t["name"], "count": t["count"],
         "pct_of_total": round(t["count"] / len(reviews) * 100, 1)}
        for t in ranked_themes[:3]
    ],
    "quotes": quotes,
    "actions": actions,
    "emerging_issue": emerging_issue,
    "other_bucket_count": len(other_bucket),
}

(OUTPUT / "pulse_draft.json").write_text(
    json.dumps(pulse_draft_payload, indent=2, ensure_ascii=False), encoding="utf-8"
)
log.info("Written: output/pulse_draft.json")

# ---------------------------------------------------------------------------
# 4. Rendered Artifacts
# ---------------------------------------------------------------------------
log.info("=== Phase 4 prep: Rendered Artifacts ===")

def star_str(rating: int) -> str:
    return "\u2605" * rating + "\u2606" * (5 - rating)

# --- Markdown pulse ---
md_lines = [
    f"# Weekly Pulse \u2014 Week ending {week_ending}",
    "",
    "## Top Themes",
]
for i, t in enumerate(ranked_themes[:3], 1):
    pct = round(t["count"] / len(reviews) * 100, 1)
    md_lines.append(f"{i}. **{t['name'].title()}** ({t['count']} reviews, {pct}%)")
if len(ranked_themes) < 3:
    for i in range(len(ranked_themes) + 1, 4):
        md_lines.append(f"{i}. N/A")

md_lines += ["", "## User Voices"]
for q in quotes:
    role_tag = {"pain": "Pain", "praise": "Praise", "fallback": "Signal", "emerging": "Emerging"}.get(q.get("role",""), "")
    md_lines.append(
        f'- *[{role_tag}]* "{q["text"]}" \u2014 {star_str(q["rating"])}, {q["date"][:10]}'
    )

md_lines += ["", "## Action Ideas"]
for a in actions:
    md_lines.append(f"{a['slot']}. {a['action']}")

if emerging_issue:
    md_lines += ["", "## Emerging Issue", emerging_issue]

markdown_pulse = "\n".join(md_lines)

# --- Plain text email body ---
def plain_stars(rating: int) -> str:
    return "*" * rating + "-" * (5 - rating)

email_lines = [
    f"Weekly App Feedback Pulse — Week ending {week_ending}",
    "=" * 55,
    "",
    f"Analysed {len(reviews)} reviews from {week_ending[:7]}.",
    "",
    "TOP THEMES",
    "-" * 30,
]
for i, t in enumerate(ranked_themes[:3], 1):
    email_lines.append(f"  {i}. {t['name'].title()} ({t['count']} reviews)")

email_lines += ["", "USER VOICES", "-" * 30]
for q in quotes:
    email_lines.append(f'  "{q["text"][:200]}"')
    email_lines.append(f"  {plain_stars(q['rating'])}  {q['date'][:10]}")
    email_lines.append("")

email_lines += ["ACTION IDEAS", "-" * 30]
for a in actions:
    email_lines.append(f"  {a['slot']}. {a['action']}")

if emerging_issue:
    email_lines += ["", "EMERGING ISSUE", "-" * 30, f"  {emerging_issue}"]

email_body = "\n".join(email_lines)

rendered_payload = {
    "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "week_ending": week_ending,
    "markdown_pulse": markdown_pulse,
    "email_subject": f"Weekly App Feedback Pulse \u2014 Week ending {week_ending}",
    "email_body_plain": email_body,
    "pulse_file_path": f"data/pulse_{week_ending}.md",
    "stats_summary": {
        "total_reviews": len(reviews),
        "themes_matched": sum(t["count"] for t in ranked_themes),
        "themes_unmatched": len(other_bucket),
        "quotes_selected": len(quotes),
        "actions_generated": len(actions),
    },
}

# Also write the markdown pulse to data/
pulse_md_path = ROOT / "data" / f"pulse_{week_ending}.md"
pulse_md_path.parent.mkdir(exist_ok=True)
pulse_md_path.write_text(markdown_pulse, encoding="utf-8")

(OUTPUT / "rendered_artifacts.json").write_text(
    json.dumps(rendered_payload, indent=2, ensure_ascii=False), encoding="utf-8"
)
log.info("Written: output/rendered_artifacts.json")
log.info("Written: data/pulse_%s.md", week_ending)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("  OUTPUT ARTIFACTS GENERATED")
print("=" * 60)
print(f"\n  [OK] output/normalised_reviews.json  ({len(reviews)} reviews)")
print(f"  [OK] output/analyzed_themes.json     ({len(ranked_themes)} themes ranked)")
print(f"  [OK] output/pulse_draft.json         ({len(quotes)} quotes, {len(actions)} actions)")
print(f"  [OK] output/rendered_artifacts.json  (markdown + email body)")
print(f"  [OK] data/pulse_{week_ending}.md")
print()
print("  Theme breakdown:")
for t in ranked_themes:
    pct = round(t["count"] / len(reviews) * 100, 1)
    bar = "|" * min(t["count"], 40)
    print(f"    {t['name']:<15} {t['count']:>4} reviews  ({pct:>5.1f}%)  {bar}")
pct_other = round(len(other_bucket) / len(reviews) * 100, 1)
print(f"    {'[other]':<15} {len(other_bucket):>4} reviews  ({pct_other:>5.1f}%)  (not in pulse)")
print()
print(f"  Week ending : {week_ending}")
print(f"  Avg rating  : {round(sum(r.rating for r in reviews)/len(reviews), 2)} / 5.00")
print()
