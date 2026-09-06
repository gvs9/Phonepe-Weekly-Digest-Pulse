# Mobile-Store Feedback — Phase-wise Implementation Plan

> Based on [`architecture.md`](./architecture.md) and [`docs/problemStatement.txt`](./docs/problemStatement.txt)

---

## Overview

The project is broken into **6 phases**, each delivering a working, testable increment:

| Phase | Name | Deliverable |
|---|---|---|
| 1 | Foundation & Data Ingestion | Normalised review dataset from store exports |
| 2 | Thematic Grouping | Reviews clustered into ≤ 5 named themes |
| 3 | Pulse Generator | Structured pulse object (themes, quotes, actions) |
| 4 | **Groq LLM Polish** | **Polished report prose + final email copy via Groq LLM** |
| 5 | Google Docs Integration | Pulse written to a live Google Doc |
| 6 | Gmail Integration & Orchestration | Gmail draft created; full pipeline wired end-to-end |

---

## Phase 1 — Foundation & Data Ingestion

### Goal
Set up the project skeleton and build the ingestion layer that loads, validates, and normalises raw review exports.

### Tasks

- [ ] **1.1 — Project scaffold**
  - Create the directory structure from `architecture.md §5`
  - Add `requirements.txt` with initial dependencies (`pandas`, `pyyaml`, `python-dateutil`)
  - Create `config.yaml` with the schema from `architecture.md §4`
  - Add `.gitignore`, `README.md` stub

- [ ] **1.2 — Review schema**
  - Define the `Review` dataclass in `ingestion/__init__.py`:
    ```
    id, source, rating, title, text, date
    ```
  - Add input validation (non-empty `text`, valid rating 1–5, parseable date)

- [ ] **1.3 — Parser (`ingestion/parser.py`)**
  - `parse_reviews(filepath: str) -> List[Review]`
  - Support CSV, JSON, and TSV input formats (auto-detect by extension)
  - Map platform-specific column names to the canonical schema
  - De-duplicate on `(source, id)` or `(source, text, date)`

- [ ] **1.4 — Date filtering**
  - `filter_by_window(reviews, weeks=10) -> List[Review]`
  - Read `review_window_weeks` from `config.yaml`
  - Filter to reviews within the last N weeks from today

- [ ] **1.5 — Sample data**
  - Add sample CSV files to `data/reviews/` (App Store + Play Store format)
  - Write a smoke test: load sample data, assert schema and count

### Acceptance Criteria
- Running `python main.py --phase 1` prints a summary: total reviews loaded, date range, source breakdown.
- All reviews have non-empty `text` and a valid `date`.

### Dependencies
```
pandas>=2.0
pyyaml>=6.0
python-dateutil>=2.8
```

---

## Phase 2 — Thematic Grouping

### Goal
Assign each normalised review to one of ≤ 5 configurable themes using keyword matching.

### Tasks

- [x] **2.1 — Theme model (`themes/__init__.py`)**
  - Define `Theme` dataclass: `name, keywords, reviews: List[Review], count`
  - Define `ThemeConfig`: load theme definitions from `config.yaml`

- [x] **2.2 — Keyword-based clusterer (`themes/clusterer.py`)**
  - `assign_themes(reviews, theme_config) -> List[Theme]`
  - For each review, scan `text` + `title` for keyword matches (case-insensitive)
  - Assign to **first matching** theme (priority order = config order)
  - Reviews that match no theme → assigned to a catch-all `"other"` bucket (excluded from pulse)

- [x] **2.3 — Theme ranking**
  - `rank_themes(themes) -> List[Theme]` — sort descending by `count`
  - Return only named themes (exclude `"other"`)

- [x] **2.4 — Config validation**
  - Raise a clear error if more than 5 themes are defined in `config.yaml`
  - Warn if any theme has zero matches

- [x] **2.5 — Unit tests**
  - Test keyword matching: exact, case-insensitive, multi-word keyword
  - Test priority: review matching two themes gets the first one
  - Test ranking output order

### Acceptance Criteria
- ✅ Running `python main.py --phase 2` prints each theme with its review count and percentage of total.
- ✅ No theme has zero reviews (or a clear warning is shown).

### Sample Output
```
Theme Results (week ending 2024-03-17)
──────────────────────────────────────
payments      42 reviews  (34%)
onboarding    28 reviews  (23%)
KYC           21 reviews  (17%)
statements    18 reviews  (15%)
withdrawals   13 reviews  (11%)
[other]        5 reviews   (not included in pulse)
```

---

## Phase 3 — Pulse Generator

### Goal
Produce the structured one-page weekly pulse note as a `PulseNote` object, saved to `data/pulse_YYYY-MM-DD.md` and printed to stdout.

---

### Data-Driven Strategy (from actual Phase 2 output)

The real review data reveals three structural realities that must shape the Phase 3 design:

#### Reality 1 — Severely skewed theme distribution
```
payments     76 reviews  (59%)   <- dominant
onboarding    2 reviews   (2%)
kyc           1 review    (1%)
statements    1 review    (1%)
withdrawals   0 reviews   (0%)
[other]      49 reviews  (38%)   <- large unmatched bucket
```
**Impact:** The naive "top 3 themes" rule breaks — themes 2/3 have only 1–2 reviews.
The pulse must still produce exactly 3 actionable sections, so we need a **fallback hierarchy**.

#### Reality 2 — Bimodal rating distribution in payments
```
payments: 5-star: 29  |  1-star: 30  (out of 76 total)
```
Average rating 2.90 / 5. Users are polarised: payments either work flawlessly or fail critically.
**Impact:** A single quote from payments doesn't represent the theme. We must pick **one pain quote and one praise quote** from the dominant theme to give the product team both signals.

#### Reality 3 — The `[other]` bucket contains rich untagged signal
The 49 unmatched reviews include account-blocking, gold/silver trading bugs, accessibility failures, and loan notification spam — none captured by the current 5 keyword sets.
**Impact:** Phase 3 must mine `[other]` to surface an **Emerging Issue** section, giving stakeholders visibility into uncategorised complaints without touching the keyword config.

---

### Revised Quote Selection Strategy
```
Slot 1 — Dominant theme (payments), pain signal:   rating <= 2, longest text
Slot 2 — Dominant theme (payments), praise signal: rating >= 4, longest text
Slot 3 — Fallback cascade (first available):
          a) Next named theme with count >= 1  →  longest review
          b) [other] bucket longest 1-star review  →  signals emerging issue
```
Guarantees exactly 3 verbatim quotes even when only 1 theme has meaningful volume.

---

### Revised Action Ideas Strategy

| Slot | Source | Rule |
|---|---|---|
| Action 1 | Dominant theme | `action_template` from config.yaml |
| Action 2 | 2nd ranked theme (or `[other]`) | config template; fallback: `"Investigate {theme} issues raised by {n} users."` |
| Action 3 | `[other]` bucket top signal | Extracted from longest 1-star unmatched reviews (keyword heuristic) |

- [ ] **3.1 — PulseNote dataclass (`pulse/__init__.py`)**
  - Fields: `week_ending: str`, `top_themes: List[Theme]`, `quotes: List[Review]`, `actions: List[str]`, `emerging_issue: Optional[str]`
  - `as_markdown() -> str` — canonical pulse format (see `architecture.md §2.3`)
  - `as_plain_text() -> str` — for Gmail body (Phase 6)

- [ ] **3.2 — Quote selector (`pulse/generator.py`)**
  - `select_quotes(ranked_themes, other_bucket) -> List[Review]` — exactly 3 verbatim quotes
  - Slot 1: dominant theme, lowest-rating + longest text (pain signal)
  - Slot 2: dominant theme, highest-rating + longest text (praise signal)
  - Slot 3: fallback cascade — next non-zero named theme → `[other]` longest 1-star review
  - Deduplication: never pick the same review twice
  - Quotes **verbatim** — zero modification

- [ ] **3.3 — Action generator (`pulse/generator.py`)**
  - `generate_actions(ranked_themes, other_bucket, config) -> List[str]` — exactly 3 actions
  - Actions 1 & 2: `action_template` from top 2 non-zero themes in config.yaml
  - Action 3: derived from the `[other]` bucket (most common complaint noun phrase from longest 5 reviews; simple word-frequency, no LLM)
  - Fallback: `"Investigate {theme} issues raised by {count} users."`

- [ ] **3.4 — Emerging issue miner (`pulse/generator.py`)**
  - `mine_emerging_issue(other_bucket) -> Optional[str]`
  - Finds the most-represented topic in the unmatched bucket (longest 1-star reviews)
  - Returns a one-sentence description for the "Emerging Issue" pulse section

- [ ] **3.5 — Pulse builder (`pulse/generator.py`)**
  - `build_pulse(ranked_themes, all_themes, config) -> PulseNote`
  - Orchestrates: `select_quotes` → `generate_actions` → `mine_emerging_issue` → `PulseNote`
  - `week_ending` = date of the most recent review in the dataset (not `date.today()`)
  - Saves pulse to `data/pulse_YYYY-MM-DD.md`; prints to stdout

- [ ] **3.6 — Markdown renderer (`pulse/__init__.py`)**
  - `PulseNote.as_markdown()` renders all 4 sections:
    - `## Top Themes` | `## User Voices` | `## Action Ideas` | `## Emerging Issue`
  - Star ratings rendered as ★/☆ via `Review.stars`
  - Theme counts included

- [ ] **3.7 — Tests (`tests/test_pulse.py`)**
  - `test_select_quotes_always_returns_3` — even with only 1 populated theme
  - `test_quotes_are_verbatim` — each quote text is a substring of the original review
  - `test_no_duplicate_quotes` — all 3 quote review IDs are distinct
  - `test_pain_slot_is_low_rated` — slot-1 rating ≤ 2
  - `test_praise_slot_is_high_rated` — slot-2 rating ≥ 4
  - `test_generate_actions_returns_3`
  - `test_as_markdown_contains_all_sections`
  - `test_pulse_file_written` — file exists at expected path

### Acceptance Criteria
- `python main.py --phase 3` produces `data/pulse_YYYY-MM-DD.md` with zero invented content.
- Pulse contains: 3 themes listed, 3 verbatim user quotes (pain + praise + fallback), 3 action ideas, 1 emerging-issue section.
- Works correctly even when only 1 named theme has ≥ 1 review.
- All 8 unit tests pass.

### Sample Output: `data/pulse_2026-08-30.md`
```markdown
# Weekly Pulse — Week ending 2026-08-30

## Top Themes
1. **Payments** (76 reviews)
2. **Onboarding** (2 reviews)
3. **KYC** (1 review)

## User Voices
- "I sold my silver through the PhonePe app, and it has been a week, but the amount has still
  not been credited to my bank account." — ★☆☆☆☆, 2026-08-15
- "No other UPI service can beat the speed of PhonePe in terms of speed. Even when I'm in low
  network areas, PhonePe always tends to be fast." — ★★★★★, 2026-08-18
- "My PhonePe UPI account has been blocked for security reasons. I have uploaded all the
  necessary documents, but my account is still blocked." — ★★★☆☆, 2026-08-29

## Action Ideas
1. Investigate the top payment failure reason and add a clear error message with a retry option.
2. Add NRI registration support (Ireland and other international numbers).
3. Investigate account-blocking reports in the unmatched bucket — users report no resolution path.

## Emerging Issue
49 reviews did not match any named theme. Top signal: account blocking and gold/silver trading
failures. Consider adding "account", "blocked", "gold", "silver" keywords to an existing theme
or creating a dedicated theme.
```

---

## Phase 4 — Groq LLM Polish

### Goal
Use the Groq API (fast LLaMA-3 inference) to upgrade the rule-based Phase 3 pulse into polished, human-quality prose — better-worded action ideas and a ready-to-send email subject/body — while keeping all verbatim quotes and data untouched.

### Context: Why Groq at This Stage
Phase 3 produces a structurally correct pulse using `config.yaml` action templates. Those templates are generic and reused every week. Groq's role is **light editorial polish only**:

| Input (Phase 3) | Output (Phase 4) |
|---|---|
| Rule-based action template | Rewritten, context-aware action idea grounded in the actual review count & quotes |
| Plain markdown pulse | Clean prose pulse with consistent tone |
| n/a | Email subject line + 2-paragraph email body for Gmail draft |

> **Hard constraint:** Groq must **never** alter, paraphrase, or invent user quotes. The `## User Voices` block is passed read-only and injected verbatim into the final output.

---

### Tasks

- [x] **4.1 — Groq client (`llm/groq_client.py`)**
  - `get_groq_client() -> Groq` — initialises the `groq` SDK client using `GROQ_API_KEY` from env / `credentials/` dir
  - `call_groq(prompt: str, system: str, max_tokens: int = 600) -> str` — single-turn call with retry on `RateLimitError` (max 3 retries, exponential backoff)
  - Model: configurable via `config.yaml` `groq_model` key (default `llama3-8b-8192`)

- [x] **4.2 — Prompt engineering (`llm/prompts.py`)**
  - `build_polish_prompt(pulse: PulseNote) -> tuple[str, str]` — returns `(system_prompt, user_prompt)`
  - **System prompt** constraints:
    - You are an editorial assistant. Improve clarity and tone only.
    - Never invent, alter, or paraphrase any user quote.
    - Output must be valid JSON matching the schema below.
    - Keep total output under 600 tokens.
  - **User prompt** injects: theme names + counts, raw action templates, emerging issue text
  - **Output schema** (JSON):
    ```json
    {
      "actions": ["action 1", "action 2", "action 3"],
      "email_subject": "string",
      "email_intro": "string (2 sentences max)"
    }
    ```
  - Verbatim quotes block is **excluded** from the prompt (not sent to LLM at all)

- [x] **4.3 — Output validator (`llm/prompts.py`)**
  - `parse_groq_response(raw: str) -> dict` — JSON-parses and validates the response
  - Checks: `actions` is a list of 3 strings, `email_subject` and `email_intro` are non-empty strings
  - On validation failure → raise `LLMOutputError` with the raw response for logging

- [x] **4.4 — PulseNote enrichment**
  - `enrich_with_llm(pulse: PulseNote, config: dict) -> PulseNote`
  - Calls `call_groq` → `parse_groq_response`
  - Returns a **new** `PulseNote` with `actions` replaced by polished versions and two new fields: `email_subject: str`, `email_intro: str`
  - Original `quotes` list is carried over verbatim — never touched by this function

- [x] **4.5 — Fallback strategy**
  - If Groq is unavailable (API key missing, rate limit exhausted, or `--dry-run`):
    - Log a `WARNING`: `"Groq unavailable — using Phase 3 rule-based output as fallback."`
    - Return the original `PulseNote` unchanged
    - Set `email_subject` = `f"Weekly App Feedback Pulse — Week ending {pulse.week_ending}"`
    - Set `email_intro` = first sentence of the pulse markdown

- [x] **4.6 — Tests (`tests/test_llm.py`)**
  - `test_parse_valid_groq_response` — valid JSON parses correctly
  - `test_parse_missing_actions_raises` — `LLMOutputError` on bad schema
  - `test_enrich_preserves_quotes` — quotes list unchanged after enrichment
  - `test_fallback_on_missing_api_key` — returns original pulse when key absent
  - `test_prompt_excludes_quotes` — user prompt string does not contain any review text

### Acceptance Criteria
- ✅ `python main.py --phase 4` produces a pulse with polished action ideas and email metadata.
- ✅ `python main.py --phase 4 --dry-run` completes without calling Groq; Phase 3 output used as-is.
- ✅ Verbatim quotes are identical before and after enrichment (byte-for-byte comparison in tests).
- ✅ All 18 unit tests pass (no live Groq call needed — prompt/parse logic is mockable).

### New Dependencies
```
groq>=0.9
python-dotenv>=1.0
```

---

## Phase 5 — Google Docs via MCP Server

### Goal
Publish the Groq-rendered pulse note into a Google Doc automatically using an MCP (Model Context Protocol) server, bypassing direct Google API integrations in the app.

### Tasks

- [x] **5.1 — MCP Client Setup**
  - Add `mcp` (Model Context Protocol python SDK) to `requirements.txt`
  - Configure the MCP server connection in `config.yaml` to use SSE (Server-Sent Events) with the endpoint URL `https://mcp-server2-production-5873.up.railway.app/sse`

- [x] **5.2 — Docs MCP Client (`integrations/mcp_client.py`)**
  - `publish_to_google_doc(pulse: PulseNote, config: dict) -> str`
  - Connect to the remote MCP server at `https://mcp-server2-production-5873.up.railway.app/sse` using the `mcp.client.sse.sse_client`
  - Call the `docs_append_content` tool provided by the server
  - Pass the formatted markdown pulse (`pulse.as_markdown()`) to the tool
  - Parse the MCP tool response to extract and return the Doc URL

- [x] **5.3 — Error handling & Fallbacks**
  - Handle MCP server connection failures gracefully (log a warning and skip)
  - Handle tool execution errors (e.g., permission denied)
  - Return `None` if publishing fails so the orchestrator can still proceed

### Acceptance Criteria
- Running `python main.py --phase 5` connects to the MCP server, creates/updates the Google Doc, and prints the Doc URL.
- Zero direct dependencies on `google-auth` or `google-api-python-client`.

### New Dependencies
```
mcp>=1.0.0
```

---

## Phase 6 — Gmail Draft via MCP Server & Full Orchestration

### Goal
Create a Gmail draft containing the pulse using the MCP server, then wire the full end-to-end pipeline into a single runnable command.

### Tasks

- [x] **6.1 — Gmail MCP Client (`integrations/mcp_client.py`)**
  - `create_gmail_draft_mcp(pulse: PulseNote, doc_url: str, config: dict) -> str`
  - Use the SSE MCP client connected to `https://mcp-server2-production-5873.up.railway.app/sse`
  - Call the `gmail_draft_email` tool provided by the server (optionally `gmail_send_email` if configured to send directly)
  - Construct the email plain-text body and HTML body featuring the Doc link
  - Return the draft ID or confirmation string

- [x] **6.2 — Email template**
  - Subject: `Weekly App Feedback Pulse — [Week ending DATE]` (from `pulse.email_subject`)
  - Body sections mirror the pulse format (from `pulse.email_intro` and `pulse.as_plain_text()`)
  - Footer: `View full pulse in Google Docs: [Doc URL]`

- [x] **6.3 — End-to-end orchestrator (`main.py`)**
  - Wire all phases into a single `run_pipeline()` function:
    ```
    reviews  = parse_reviews(data_dir)
    reviews  = filter_by_window(reviews, weeks)
    themes   = assign_themes(reviews, theme_config)
    themes   = rank_themes(themes)
    pulse    = build_pulse(themes)               # Phase 3
    pulse    = enrich_with_llm(pulse)            # Phase 4 (Groq)
    doc_url  = publish_to_google_doc(pulse)      # Phase 5 (MCP)
    draft_id = create_gmail_draft_mcp(pulse)     # Phase 6 (MCP)
    ```

### Acceptance Criteria
- Running `python main.py` with no phase arguments executes the full pipeline end-to-end.
- Output culminates in printing the Google Doc URL and the Gmail Draft ID.
- No direct Google APIs are used.
  - CLI: `python main.py` runs the full pipeline; `python main.py --phase N` runs up to phase N

- [x] **6.4 — Logging & summary**
  - Log each pipeline step with timestamp and status
  - Print final summary:
    ```
    ✅ Reviews loaded:    127
    ✅ Themes identified: 5
    ✅ Pulse generated:   data/pulse_2024-03-17.md
    ✅ Groq LLM:          report + email body generated (874 tokens)
    ✅ Google Doc:        https://docs.google.com/document/d/.../edit
    ✅ Gmail draft:       Draft ID abc123 ready in your Drafts folder
    ```

- [x] **6.5 — Integration test (dry-run mode)**
  - `python main.py --dry-run` runs the full pipeline without calling MCP tools
  - Outputs the pulse markdown and email content to stdout only

- [x] **6.6 — Documentation**
  - Update `README.md` with:
    - Setup instructions (Python version, `pip install -r requirements.txt`)
    - MCP server configuration steps
    - `config.yaml` customisation guide
    - Example run commands

- [x] **6.7 — Automated Scheduling**
  - Add GitHub Actions workflow `fetch-reviews.yml` to run the full pipeline automatically every Sunday at midnight.
  - Push output artifacts (like new Pulse reports and ingested reviews) back to the repo.

### Final Acceptance Criteria
- `python main.py` completes without error and produces:
  1. A `data/pulse_YYYY-MM-DD.md` file
  2. A Google Doc with the formatted pulse (Doc URL printed) via MCP
  3. A Gmail draft in the configured account (Draft ID printed) via MCP
- `python main.py --dry-run` completes without calling any MCP tool.

---

## Dependency Summary

```
# requirements.txt
mcp>=1.0.0
groq>=0.9
python-dotenv>=1.0
pandas>=2.0
pyyaml>=6.0
python-dateutil>=2.8
```

---

## Phase Completion Checklist

| Phase | Status | Key Output |
|---|---|---|
| 1 — Foundation & Ingestion | `[x]` ✅ | `ingestion/parser.py` + `filter_noise()` + sample data + 39 tests |
| 2 — Thematic Grouping | `[x]` ✅ | `themes/clusterer.py` + `ThemeConfig` + theme counts + 34 tests |
| 3 — Pulse Generator | `[x]` ✅ | `data/pulse_YYYY-MM-DD.md` |
| 4 — Groq LLM Polish | `[x]` ✅ | `llm/groq_client.py` + `llm/prompts.py` + 18 tests (no live call) |
| 5 — Docs & MCP setup | `[x]` ✅ | Google Doc URL generated |
| 6 — Gmail & Orchestration | `[x]` ✅ | Gmail draft + full CLI pipeline |

---

## Risk & Mitigation

| Risk | Mitigation |
|---|---|
| Platform ToS for scraping reviews | Use official exports (App Store Connect, Play Console) where possible |
| Google OAuth complexity | Use `google-auth-oauthlib` flow with a local redirect; document clearly |
| Low review volume for some themes | Add a `min_reviews` threshold; warn and skip themes below it |
| Verbatim quote quality | Select by length (>50 chars) to avoid trivially short reviews |
| Action idea relevance | Maintain per-theme action templates in `config.yaml`; allow overrides |
| Groq hallucinating quotes | System prompt explicitly forbids invented quotes; assert verbatim match in tests |
| Groq API rate limits / downtime | Fallback to templated Phase 3 output; surface a clear warning in logs |
| LLM output too long for Gmail | Cap max_tokens=600; truncate gracefully with a "...see full report in Docs" note |






---

## Output Artifacts (Generated)

All artifacts are written to the `output/` folder by running `python generate_output.py`.

| Artifact | Phase | Description |
|---|---|---|
| `output/normalised_reviews.json` | 1 | All reviews post-ingestion: schema, date filter, source/rating breakdown, full review list |
| `output/analyzed_themes.json` | 2 | Theme assignment results: ranked buckets, per-theme stats, review-to-theme mapping |
| `output/pulse_draft.json` | 3 | Structured pulse: top 3 themes, 3 verbatim quotes (pain/praise/fallback), 3 actions, emerging issue |
| `output/rendered_artifacts.json` | 3 | Final rendered surfaces: markdown pulse, email subject, plain-text email body, pulse file path |
| `data/pulse_YYYY-MM-DD.md` | 3 | Markdown pulse written to disk (date = latest review date) |

### Last Run Results (PhonePe, week ending 2026-08-30)

```
Reviews loaded      : 129  (from 1000 fetched; 871 filtered as noise/non-English)
Date range          : 2026-06-11  ->  2026-08-30
Average rating      : 2.90 / 5.00

Theme breakdown:
  payments          76  (58.9%)
  onboarding         2   (1.6%)
  kyc                1   (0.8%)
  statements         1   (0.8%)
  withdrawals        0   (0.0%)
  [other]           49  (38.0%)  <- not in pulse; mined for emerging issue
```

### Regenerate
```bash
python generate_output.py
```
