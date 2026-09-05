# Mobile-Store Feedback

A pipeline that turns raw App Store / Play Store reviews into a weekly one-page pulse and delivers it via Google Docs and Gmail.

## Phases
| Phase | Status | Description |
|---|---|---|
| 1 | ✅ | Foundation & Data Ingestion |
| 2 | 🔲 | Thematic Grouping |
| 3 | 🔲 | Pulse Generator |
| 4 | 🔲 | Groq LLM Polish |
| 5 | 🔲 | Google Docs Integration |
| 6 | 🔲 | Gmail Integration & Orchestration |

## Quick Start

```bash
pip install -r requirements.txt
python main.py --phase 1
```

## Configuration
Edit `config.yaml` before running:
- Set `review_window_weeks` (8–12)
- Customise `themes` and their `keywords` for your product
- Set `gmail_recipient` (Phase 6)
- Set `google_doc_id` or leave blank to auto-create (Phase 5)
- Add `GROQ_API_KEY` to a `.env` file (Phase 4)

## Data Input
Place review exports in `data/reviews/`:
- App Store: `data/reviews/appstore_reviews.csv`
- Play Store: `data/reviews/playstore_reviews.json`

Supported formats: CSV, JSON, TSV

## Project Structure
```
Mobile-Store Feedback/
├── config.yaml          # All tuneable parameters
├── main.py              # Pipeline entry point
├── ingestion/           # Review loading & normalisation (Phase 1)
├── themes/              # Keyword-based thematic grouping (Phase 2)
├── pulse/               # Weekly note generator (Phase 3)
├── llm/                 # Groq LLM integration (Phase 4)
├── integrations/        # Google Docs & Gmail (Phases 5–6)
└── data/reviews/        # Place raw export files here
```
