# Mobile-Store Feedback — Architecture

> Derived from [`docs/problemStatement.txt`](./docs/problemStatement.txt) and [`context.md`](./context.md)

---

## 1. Overview

The system is a **pipeline** that ingests raw App Store / Play Store reviews, runs NLP-style thematic analysis, produces a structured one-page weekly pulse, and delivers it through two Google surfaces (Docs + Gmail) — all without requiring the developer to handle credentials or low-level REST wiring directly.

```
┌─────────────────────┐
│   Review Sources    │  App Store  |  Play Store
└────────┬────────────┘
         │  (CSV / JSON export or scraper)
         ▼
┌─────────────────────┐
│   Data Ingestion    │  Parse, normalise, filter (last 8–12 weeks)
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Thematic Grouping  │  Cluster into ≤ 5 themes
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Pulse Generator    │  Top 3 themes · 3 quotes · 3 action ideas
└────────┬────────────┘
         │
         ├──────────────────────────────┐
         ▼                              ▼
┌─────────────────┐          ┌─────────────────────┐
│   Google Docs   │          │       Gmail          │
│  (pulse note)   │          │  (draft email)       │
└─────────────────┘          └─────────────────────┘
```

---

## 2. Components

### 2.1 Review Ingestion (`ingestion/`)

**Responsibility:** Load raw review data and normalise it into a consistent schema.

| Field | Type | Notes |
|---|---|---|
| `id` | string | Unique review identifier |
| `source` | enum | `app_store` \| `play_store` |
| `rating` | int | 1–5 |
| `title` | string | Review title (may be empty) |
| `text` | string | Full review body |
| `date` | date | Review submission date |

- Accepts any export format the platform provides (CSV, JSON, TSV).
- Filters to reviews within the **last 8–12 weeks** relative to run date.
- Strips duplicates and entries with empty `text`.

---

### 2.2 Thematic Grouping (`themes/`)

**Responsibility:** Cluster normalised reviews into a small, meaningful set of themes.

- Maximum **5 themes** per run.
- Themes are product-specific (e.g. onboarding, KYC, payments, statements, withdrawals).
- Each review is assigned to exactly **one** primary theme.
- Theme labels and keywords are **configurable** (not hard-coded).

**Suggested approach:**
- Keyword / rule-based matching (fast, deterministic, auditable), OR
- Embedding-based clustering (k-means / HDBSCAN) for larger review volumes.
- Output: a list of `Theme` objects, each with a label, matched reviews, and a frequency count.

---

### 2.3 Pulse Generator (`pulse/`)

**Responsibility:** Produce the one-page weekly note from the theme analysis output.

Output structure:

```
Weekly Pulse — [Week ending DATE]

Top Themes
──────────
1. [Theme A]  (n reviews)
2. [Theme B]  (n reviews)
3. [Theme C]  (n reviews)

User Voices
───────────
• "[Verbatim quote 1]" — ★★★☆☆, [Date]
• "[Verbatim quote 2]" — ★★★★★, [Date]
• "[Verbatim quote 3]" — ★★☆☆☆, [Date]

Action Ideas
────────────
1. [Concrete action grounded in Theme A]
2. [Concrete action grounded in Theme B]
3. [Concrete action grounded in Theme C]
```

Rules:
- Quotes must be **verbatim** — no paraphrasing or invented text.
- Action ideas must be **directly traceable** to a theme.
- The generator selects the **top 3** themes by review volume.

---

### 2.4 Google Docs Integration (`integrations/docs.py`)

**Responsibility:** Write the pulse note into a Google Doc.

- Creates or updates a designated Google Doc with the pulse content.
- Uses the **Google Docs API** (via an MCP tool or the official client library).
- The Doc URL / ID is stored in config and returned as output for linking in the email.
- No manual OAuth flow required by the developer — handled through the integration layer.

---

### 2.5 Gmail Integration (`integrations/gmail.py`)

**Responsibility:** Create a Gmail draft containing or linking to the weekly pulse.

- Composes a draft email addressed to the configured recipient (self or alias).
- Email body includes the full pulse text **and/or** a link to the Google Doc.
- Uses the **Gmail API** (via an MCP tool or the official client library).
- Saved as a **draft** — the user reviews and sends manually.
- No manual OAuth flow required by the developer.

---

## 3. Data Flow (Detailed)

```
[Raw Export File(s)]
        │
        │  parse_reviews(file) → List[Review]
        ▼
[Normalised Reviews]  ← filter: date within 8–12 weeks
        │
        │  assign_themes(reviews, theme_config) → List[Theme]
        ▼
[Themed Review Buckets]
        │
        │  build_pulse(themes) → PulseNote
        ▼
[PulseNote]
        ├──  write_to_docs(pulse) → doc_url
        └──  create_gmail_draft(pulse, doc_url) → draft_id
```

---

## 4. Configuration

All tuneable parameters live in a single config file (e.g. `config.yaml` or `.env`):

```yaml
# Review window
review_window_weeks: 10          # 8–12, adjust per run

# Themes (product-specific)
themes:
  - name: onboarding
    keywords: [signup, register, first time, welcome, tutorial]
  - name: payments
    keywords: [pay, payment, transfer, transaction, failed]
  - name: KYC
    keywords: [kyc, verify, document, identity, id check]
  - name: statements
    keywords: [statement, history, export, download, pdf]
  - name: withdrawals
    keywords: [withdraw, cash out, redeem, payout]

# Delivery
google_doc_id: "<YOUR_DOC_ID>"
gmail_recipient: "you@example.com"
```

---

## 5. Directory Structure (Proposed)

```
Mobile-Store Feedback/
├── docs/
│   └── problemStatement.txt
├── context.md
├── architecture.md
├── config.yaml                   # tuneable parameters
├── data/
│   └── reviews/                  # raw export files go here
├── ingestion/
│   ├── __init__.py
│   └── parser.py                 # parse + normalise reviews
├── themes/
│   ├── __init__.py
│   └── clusterer.py              # theme assignment logic
├── pulse/
│   ├── __init__.py
│   └── generator.py              # build the one-page note
├── integrations/
│   ├── __init__.py
│   ├── docs.py                   # Google Docs writer
│   └── gmail.py                  # Gmail draft creator
└── main.py                       # orchestrator / entry point
```

---

## 6. Integration Strategy

| Surface | API | Auth mechanism |
|---|---|---|
| App Store reviews | RSS feed / `app-store-scraper` library | None (public) |
| Play Store reviews | `google-play-scraper` library | None (public) |
| Google Docs | Google Docs API v1 | OAuth 2.0 / Service Account |
| Gmail | Gmail API v1 | OAuth 2.0 / Service Account |

> Credential management is handled by the Google Auth library (`google-auth`) using a service account JSON key or user OAuth token — **not** implemented manually by the developer.

---

## 7. Key Design Decisions

| Decision | Rationale |
|---|---|
| ≤ 5 themes | Keeps the pulse scannable; avoids analysis paralysis |
| Verbatim quotes only | Prevents hallucinated or misleading attribution |
| Gmail draft (not send) | Gives the user a final review step before delivery |
| Google Docs as the canonical store | Stakeholders can access any week''s pulse via a shared link |
| Config-driven themes | Teams with different products can adapt without code changes |
| 8–12 week window | Balances recency with enough volume for statistical significance |
| Vendoring Dependencies | `app-store-scraper` is vendored directly into the repository to permanently resolve pip dependency conflicts (specifically around legacy `requests` pinning) in modern cloud environments like Streamlit Cloud. |

---

## 8. Non-Goals

- Real-time review monitoring (this is a weekly batch job).
- Sentiment scoring or star-rating prediction beyond grouping.
- Multi-language review support (English assumed unless extended).
- Automated email sending (draft-only by design).
