# Mobile-Store Feedback -- Edge Cases & Corner Case Handling

> Covers all 6 pipeline phases: Ingestion, Thematic Grouping, Pulse Generator, Groq LLM Polish, Google Docs, Gmail

---

## How to Use This Document

Each edge case follows this format:

| Field | Meaning |
|---|---|
| **ID** | Unique reference (e.g. `ING-01`) |
| **Phase** | Which pipeline stage is affected |
| **Scenario** | What can go wrong |
| **Risk** | Impact if unhandled |
| **Detection** | How to identify the condition |
| **Handling** | What the code should do |
| **Test** | How to verify the fix |

---

## Phase 1 -- Data Ingestion

### ING-01: Empty review file

| | |
|---|---|
| **Scenario** | The import file exists but contains zero data rows (header only or truly empty) |
| **Risk** | Pipeline runs silently and produces a meaningless pulse |
| **Detection** | `len(reviews) == 0` after parsing |
| **Handling** | Raise `InsufficientDataError("No reviews found in file")` and exit with code 1 |
| **Test** | Pass an empty CSV; assert `InsufficientDataError` is raised |

---

### ING-02: All reviews fall outside the date window

| | |
|---|---|
| **Scenario** | File has rows but all dates are older than the configured 8--12 week window |
| **Risk** | Pipeline produces a pulse from zero reviews |
| **Detection** | `len(filtered_reviews) == 0` after `filter_by_window()` |
| **Handling** | Log warning; raise `InsufficientDataError("0 reviews in the last N weeks")` |
| **Test** | Load reviews all dated 6 months ago with window=10; assert error is raised |

---

### ING-03: Missing or unrecognised columns

| | |
|---|---|
| **Scenario** | Export file is missing required columns (e.g. no `date` or no `text` column) |
| **Risk** | `KeyError` crash or silently missing data |
| **Detection** | Check expected columns after loading; compare against schema |
| **Handling** | Raise `SchemaError("Missing columns: [date, text]")` with the exact missing fields listed |
| **Test** | Pass a CSV with only `rating` column; assert `SchemaError` lists missing columns |

---

### ING-04: Unparseable dates

| | |
|---|---|
| **Scenario** | Some rows have malformed date strings (e.g. `"31-13-2024"`, `"N/A"`, empty string) |
| **Risk** | Crash or incorrect date filtering |
| **Detection** | Wrap date parsing in try/except; log bad rows |
| **Handling** | Skip rows with unparseable dates; log `"Skipped review {id}: invalid date '{raw}'"` |
| **Test** | Include 2 bad-date rows in a 10-row fixture; assert 8 reviews loaded |

---

### ING-05: Duplicate reviews

| | |
|---|---|
| **Scenario** | Same review appears more than once (e.g. merged App Store + Play Store export with overlap) |
| **Risk** | Theme counts inflated; same quote selected multiple times |
| **Detection** | De-duplicate on `(source, id)` or `(source, text[:100], date)` |
| **Handling** | Keep first occurrence; log count of duplicates dropped |
| **Test** | Load a file with 5 duplicate pairs; assert output has 5 unique reviews |

---

### ING-06: Review with empty text

| | |
|---|---|
| **Scenario** | Row has a rating but the `text` field is empty or whitespace-only |
| **Risk** | Empty string passed to theme matcher; selected as a verbatim quote |
| **Detection** | `review.text.strip() == ""` |
| **Handling** | Drop the row; log `"Skipped review {id}: empty text"` |
| **Test** | Include 3 blank-text rows; assert they are absent from output |

---

### ING-07: Mixed timezones in date fields

| | |
|---|---|
| **Scenario** | Some dates include timezone offsets (e.g. `2024-03-14T10:00:00+05:30`), others are naive |
| **Risk** | Timezone-aware vs naive comparison raises `TypeError` |
| **Detection** | Check `tzinfo` on each parsed date |
| **Handling** | Normalise all dates to UTC on ingest; store as timezone-aware datetimes |
| **Test** | Mix TZ-aware and naive dates in fixture; assert all are normalised to UTC |

---

### ING-08: Very large file (10,000+ reviews)

| | |
|---|---|
| **Scenario** | Export contains months of reviews far exceeding the window |
| **Risk** | High memory usage; slow processing |
| **Detection** | File size > 5 MB or row count > 5,000 |
| **Handling** | Stream-parse with chunked pandas `read_csv(chunksize=1000)`; apply date filter per chunk |
| **Test** | Generate a 15,000-row fixture; assert memory stays below threshold and run time < 30s |

---

## Phase 2 -- Thematic Grouping

### THM-01: Review matches no theme

| | |
|---|---|
| **Scenario** | A review contains none of the configured keywords for any theme |
| **Risk** | Review silently dropped; theme counts undercount real sentiment |
| **Detection** | After assignment, count reviews with `theme == "other"` |
| **Handling** | Assign to `"other"` bucket; log count; exclude from pulse but surface in summary stats |
| **Test** | Include 5 reviews with unique unrelated words; assert all land in `"other"` |

---

### THM-02: Review matches multiple themes

| | |
|---|---|
| **Scenario** | Review text contains keywords for both `payments` and `KYC` (e.g. "KYC failed during payment") |
| **Risk** | Ambiguous assignment; same review counted twice |
| **Detection** | Match loop finds hits in more than one theme |
| **Handling** | Assign to the **first matching theme** in config order (priority = config order); never double-count |
| **Test** | Write a review matching themes 1 and 3; assert it is assigned to theme 1 only |

---

### THM-03: All reviews land in one theme

| | |
|---|---|
| **Scenario** | 95% of reviews match only `payments`; other themes have 0--1 reviews |
| **Risk** | Pulse is dominated by one theme; actionability is low |
| **Detection** | Any theme with `count < min_reviews` threshold (configurable, default: 3) |
| **Handling** | Warn: `"Theme 'KYC' has only 1 review -- may not be statistically significant"`; still include if top-3 |
| **Test** | Configure 5 themes; feed reviews that all match theme 1; assert warnings are logged for others |

---

### THM-04: More than 5 themes configured

| | |
|---|---|
| **Scenario** | User defines 7 themes in `config.yaml` |
| **Risk** | Violates the architecture constraint; cluttered pulse |
| **Detection** | `len(theme_config) > 5` at startup |
| **Handling** | Raise `ConfigError("Too many themes: 7 defined, maximum is 5")` before any processing |
| **Test** | Load a config with 6 themes; assert `ConfigError` is raised immediately |

---

### THM-05: Zero themes configured

| | |
|---|---|
| **Scenario** | `config.yaml` themes list is empty |
| **Risk** | All reviews land in `"other"`; no pulse is possible |
| **Detection** | `len(theme_config) == 0` at startup |
| **Handling** | Raise `ConfigError("No themes defined in config.yaml")` |
| **Test** | Load empty themes list; assert `ConfigError` |

---

### THM-06: Keyword is a very common English word

| | |
|---|---|
| **Scenario** | A keyword like `"check"` or `"update"` matches almost every review |
| **Risk** | One theme vacuums up unrelated reviews |
| **Detection** | Not automatically detectable -- a design/config risk |
| **Handling** | Document in `config.yaml` comments: use multi-word phrases or specific domain terms; log a warning if any single theme captures >60% of reviews |
| **Test** | Set keyword to `"the"`; assert a >60% capture warning is logged |

---

## Phase 3 -- Pulse Generator

### PLS-01: Fewer than 3 themes have enough reviews

| | |
|---|---|
| **Scenario** | Only 2 themes have reviews; the pulse requires 3 |
| **Risk** | Pulse is malformed or crashes trying to access `themes[2]` |
| **Detection** | `len(ranked_themes) < 3` |
| **Handling** | Use however many themes exist (1 or 2); label missing slots as `N/A`; log a warning |
| **Test** | Feed reviews matching only 2 themes; assert pulse has 2 theme entries, not 3 |

---

### PLS-02: No quote long enough to be meaningful

| | |
|---|---|
| **Scenario** | All reviews in the top theme are very short (e.g. "Bad app", "Love it") -- under 30 characters |
| **Risk** | Pulse contains useless one-liner quotes |
| **Detection** | `len(review.text.strip()) < 30` for all candidates in a theme |
| **Handling** | Relax the length threshold progressively (50 → 30 → 10); if still nothing, use the longest available and log a warning |
| **Test** | Feed a theme with only 5-word reviews; assert the longest one is selected and warning is logged |

---

### PLS-03: Action template missing for a theme

| | |
|---|---|
| **Scenario** | A theme appears in the top 3 but has no `action_template` defined in `config.yaml` |
| **Risk** | Action idea slot is blank or crashes |
| **Detection** | `theme.action_template is None` |
| **Handling** | Use a generic fallback: `"Investigate the top complaints in the '{theme_name}' category and prioritise a fix."` |
| **Test** | Remove an action template from config; assert the fallback string is used in the pulse |

---

### PLS-04: Week-ending date edge cases

| | |
|---|---|
| **Scenario** | Pipeline runs at 23:59 on Sunday vs 00:01 on Monday -- which week? |
| **Risk** | Inconsistent pulse dates if run time is near a week boundary |
| **Detection** | Always compute `week_ending` as the most recent Sunday (or configurable day) relative to run date |
| **Handling** | Pin `week_ending = last_day_of_iso_week(date.today())` regardless of run time |
| **Test** | Run with mocked date of Monday 00:01; assert `week_ending` is the previous Sunday |

---

## Phase 4 -- Groq LLM Polish

### LLM-01: Groq API key missing or invalid

| | |
|---|---|
| **Scenario** | `GROQ_API_KEY` is not set in the environment or `.env` file, or is revoked |
| **Risk** | `AuthenticationError` crash |
| **Detection** | Check `os.getenv("GROQ_API_KEY")` is non-empty at startup |
| **Handling** | If missing: raise `ConfigError("GROQ_API_KEY not set -- add it to .env")`; if API rejects it: log and fall back to Phase 3 templated output |
| **Test** | Run with `GROQ_API_KEY=""` and assert fallback output is used |

---

### LLM-02: Groq returns a truncated response

| | |
|---|---|
| **Scenario** | LLM hits `max_tokens` mid-sentence; output is cut off |
| **Risk** | Incomplete report sent to Docs or email |
| **Detection** | `response.choices[0].finish_reason == "length"` |
| **Handling** | Log warning; append `"\n\n[Report truncated -- view full analysis in source data]"` to the output |
| **Test** | Mock Groq to return `finish_reason="length"` with truncated content; assert suffix is appended |

---

### LLM-03: LLM invents or paraphrases a quote

| | |
|---|---|
| **Scenario** | Groq modifies a quote slightly (e.g. fixing grammar, summarising) |
| **Risk** | Fabricated attribution -- critical integrity violation |
| **Detection** | Post-generation: for each quote in `pulse.quotes`, assert it appears as a substring in `polished_report` exactly |
| **Handling** | If any quote is missing from the report: log `"INTEGRITY WARNING: quote not found verbatim in LLM output"`; replace the LLM output section with the raw templated quotes |
| **Test** | Mock LLM to return a report with a slightly altered quote; assert integrity check fires and raw quotes are used |

---

### LLM-04: Groq rate limit exceeded

| | |
|---|---|
| **Scenario** | Too many API calls in a short window; `RateLimitError` thrown |
| **Risk** | Pipeline halts |
| **Detection** | Catch `groq.RateLimitError` |
| **Handling** | Exponential backoff: wait 5s, 15s, 45s; after 3 retries fall back to templated output |
| **Test** | Mock Groq to raise `RateLimitError` 3 times; assert fallback is used after 3 retries |

---

### LLM-05: Groq returns empty or whitespace-only content

| | |
|---|---|
| **Scenario** | API call succeeds but `message.content` is `""` or `"   "` |
| **Risk** | Empty report written to Google Doc |
| **Detection** | `response.choices[0].message.content.strip() == ""` |
| **Handling** | Treat as a failed call; fall back to templated Phase 3 output; log warning |
| **Test** | Mock Groq to return empty content; assert fallback output is used |

---

### LLM-06: Groq response is not valid markdown

| | |
|---|---|
| **Scenario** | LLM returns plain text or JSON instead of the requested markdown structure |
| **Risk** | Google Doc formatting is broken |
| **Detection** | Check response contains expected section headers (e.g. `##`) |
| **Handling** | Wrap plain text in a minimal markdown structure; log `"LLM output was not markdown -- wrapped"` |
| **Test** | Mock LLM to return a plain paragraph; assert it is wrapped with section headers |

---

## Phase 5 -- Google Docs Integration

### DOC-01: Google Doc ID not configured

| | |
|---|---|
| **Scenario** | `google_doc_id` is blank in `config.yaml` on first run |
| **Risk** | API call fails with a confusing error |
| **Detection** | `config.google_doc_id` is `None` or `""` |
| **Handling** | Auto-create a new Doc; write the new ID back to `config.yaml`; print: `"New Doc created: https://docs.google.com/document/d/{id}/edit"` |
| **Test** | Run with empty `google_doc_id`; assert a new Doc is created and the ID is persisted to config |

---

### DOC-02: Insufficient permissions (403)

| | |
|---|---|
| **Scenario** | Service account / OAuth token does not have write access to the target Doc |
| **Risk** | `HttpError 403` crash |
| **Detection** | Catch `googleapiclient.errors.HttpError` with `status == 403` |
| **Handling** | Print actionable message: `"Permission denied on Doc {id}. Share the Doc with {service_account_email} as Editor."` then exit |
| **Test** | Mock the Docs API to return 403; assert the message contains "Share the Doc" |

---

### DOC-03: Doc ID not found (404)

| | |
|---|---|
| **Scenario** | The configured Doc was deleted or the ID is wrong |
| **Risk** | `HttpError 404` crash |
| **Detection** | Catch `HttpError` with `status == 404` |
| **Handling** | Prompt: `"Doc not found. Creating a new one..."` then auto-create and update config |
| **Test** | Mock 404 response; assert new Doc is created |

---

### DOC-04: Doc content exceeds API request size

| | |
|---|---|
| **Scenario** | Pulse + historical entries make the `batchUpdate` request too large |
| **Risk** | `HttpError 400` -- payload too large |
| **Detection** | `len(json.dumps(requests)) > 10_000_000` (10 MB Docs API limit) |
| **Handling** | Split into multiple `batchUpdate` calls; or rotate to a new Doc for the new month |
| **Test** | Mock a pulse that generates a >10MB request; assert it is split correctly |

---

### DOC-05: Transient network failure

| | |
|---|---|
| **Scenario** | `HttpError 500/503` or `socket.timeout` during Docs API call |
| **Risk** | Data not written; pipeline reports success incorrectly |
| **Detection** | Catch `HttpError` with `status >= 500` and `socket.timeout` |
| **Handling** | Retry up to 3 times with exponential backoff (2s, 8s, 32s); if all fail, log error and exit with code 1 |
| **Test** | Mock 3 consecutive 503 responses; assert 3 retries then failure |

---

## Phase 6 -- Gmail Integration

### MAIL-01: Recipient address not configured

| | |
|---|---|
| **Scenario** | `gmail_recipient` is blank in `config.yaml` |
| **Risk** | Draft created with no To: address (or crash) |
| **Detection** | `config.gmail_recipient` is `None` or `""` at startup |
| **Handling** | Raise `ConfigError("gmail_recipient is not set in config.yaml")` before the Gmail call |
| **Test** | Run with empty recipient; assert `ConfigError` before any API call |

---

### MAIL-02: Invalid recipient email format

| | |
|---|---|
| **Scenario** | `gmail_recipient` is set to a malformed value (e.g. `"notanemail"`) |
| **Risk** | Gmail API rejects the draft; cryptic error |
| **Detection** | Validate with regex `r"^[^@]+@[^@]+\.[^@]+"` on startup |
| **Handling** | Raise `ConfigError("gmail_recipient '{value}' is not a valid email address")` |
| **Test** | Set `gmail_recipient: "notanemail"`; assert `ConfigError` on startup |

---

### MAIL-03: Gmail draft creation fails (403 / scope error)

| | |
|---|---|
| **Scenario** | OAuth token lacks the `gmail.compose` scope |
| **Risk** | `HttpError 403 -- insufficient permissions` |
| **Detection** | Catch 403; check if error message mentions scope |
| **Handling** | Print: `"Gmail scope error. Re-authenticate with the gmail.compose scope."` then exit |
| **Test** | Mock 403 with scope message; assert user-friendly message is printed |

---

### MAIL-04: Email body is empty after LLM fallback

| | |
|---|---|
| **Scenario** | Groq failed (LLM-01/04/05) AND the templated fallback also produces empty output |
| **Risk** | Empty draft email created |
| **Detection** | `len(email_body.strip()) == 0` before creating the draft |
| **Handling** | Abort draft creation; log `"Email body is empty -- skipping Gmail draft"`; exit gracefully |
| **Test** | Mock both Groq and template to return empty strings; assert no draft is created |

---

### MAIL-05: Duplicate draft creation on retry

| | |
|---|---|
| **Scenario** | Pipeline retries after a transient error but the first draft was already saved |
| **Risk** | Multiple identical drafts in the Drafts folder |
| **Detection** | Check for an existing draft with the same subject before creating |
| **Handling** | Query existing drafts; if a draft with matching subject exists from today, update it instead of creating a new one |
| **Test** | Run pipeline twice in succession; assert only one draft exists in the mock |

---

## Cross-Cutting Edge Cases

### CC-01: `config.yaml` is missing entirely

| | |
|---|---|
| **Phase** | All |
| **Scenario** | `config.yaml` was not created or was deleted |
| **Risk** | `FileNotFoundError` crash on startup |
| **Detection** | Check file exists before loading |
| **Handling** | Print: `"config.yaml not found. Run: python main.py --init to create a default config."` then exit |
| **Test** | Run without `config.yaml`; assert exit message contains `--init` |

---

### CC-02: Pipeline interrupted mid-run

| | |
|---|---|
| **Phase** | 3--6 |
| **Scenario** | User hits Ctrl+C or process is killed between Doc write and Gmail draft creation |
| **Risk** | Doc is updated but no email draft exists; next run may duplicate the Doc entry |
| **Detection** | Write a `.pipeline_state.json` after each phase completes |
| **Handling** | On next run, read state file; skip already-completed phases; clean up partial writes |
| **Test** | Simulate SIGINT after Phase 5; re-run; assert Phase 5 is skipped and Phase 6 completes |

---

### CC-03: `--dry-run` accidentally hits a live API

| | |
|---|---|
| **Phase** | 4, 5, 6 |
| **Scenario** | A code path in dry-run mode still calls Groq or Google APIs |
| **Risk** | Unwanted side effects (charges, writes) |
| **Detection** | Gate every API call behind `if not config.dry_run` |
| **Handling** | In dry-run mode: substitute all API calls with mock no-ops; print `"[DRY-RUN] Would call Groq / Google Docs / Gmail"` |
| **Test** | Run `--dry-run`; assert zero real HTTP requests are made (patch `requests.Session.send`) |

---

### CC-04: Python version incompatibility

| | |
|---|---|
| **Phase** | All |
| **Scenario** | User runs on Python 3.8 but code uses 3.10+ syntax (e.g. `match/case`, `X | Y` union types) |
| **Risk** | `SyntaxError` on startup |
| **Detection** | Check at entry point: `sys.version_info < (3, 10)` |
| **Handling** | Print: `"Python 3.10+ required. Current: {sys.version}"` then exit |
| **Test** | Mock `sys.version_info` as `(3, 8, 0)`; assert startup error |

---

### CC-05: Credentials file missing or expired

| | |
|---|---|
| **Phase** | 5, 6 |
| **Scenario** | `credentials.json` or `token.json` is missing, or OAuth token is expired and cannot refresh |
| **Risk** | `FileNotFoundError` or silent auth failure |
| **Detection** | Catch `google.auth.exceptions.RefreshError` and `FileNotFoundError` |
| **Handling** | Print step-by-step re-auth instructions; exit with code 1 |
| **Test** | Delete `token.json`; run pipeline; assert re-auth instructions are printed |

---

## Edge Case Coverage Summary

| Phase | Total Cases | Critical |
|---|---|---|
| Phase 1 -- Ingestion | 8 | ING-01, ING-02, ING-03 |
| Phase 2 -- Theming | 6 | THM-01, THM-04, THM-05 |
| Phase 3 -- Pulse | 4 | PLS-01, PLS-03 |
| Phase 4 -- Groq LLM | 6 | LLM-01, LLM-03, LLM-04 |
| Phase 5 -- Google Docs | 5 | DOC-02, DOC-05 |
| Phase 6 -- Gmail | 5 | MAIL-01, MAIL-04 |
| Cross-cutting | 5 | CC-01, CC-02, CC-03 |
| **Total** | **39** | |
