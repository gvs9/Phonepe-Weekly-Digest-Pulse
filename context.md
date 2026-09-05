# Mobile-Store Feedback — Project Context

> Extracted from [`docs/problemStatement.txt`](./docs/problemStatement.txt)

---

## 🎯 Goal

Turn raw mobile-store reviews into a **weekly pulse** that a team can scan in minutes — surfacing what users care about, what they actually said, and what to do next.

Reviews are already public. The job is to **aggregate → theme → summarize → deliver** that insight through familiar surfaces:
- **Google Docs** — for the written weekly pulse
- **Gmail** — for a draft email the user can send to themselves (or an alias)

No manual credential handling or raw REST wiring required.

---

## 🔄 End-to-End Flow

1. **Pull** recent App Store and Play Store reviews for the target product.
2. **Cluster** them into a small set of themes and distill a one-page weekly note.
3. **Publish** that note to Google Docs where stakeholders can read it.
4. **Draft** an email (via Gmail) to yourself or an alias containing or linking to the pulse.

---

## 📦 Deliverables

### Weekly One-Page Pulse
Must include:
- **Top themes** — what users are talking about most
- **Real user quotes** — verbatim snippets from reviews (no invented wording)
- **Three action ideas** — concrete next steps grounded in the themes

### Draft Email
- Contains the weekly note (or a clear link/pointer to it)
- Sent as a Gmail draft to the user or a specified alias

---

## 👥 Target Audience

| Audience | Why It Matters |
|---|---|
| **Product / Growth** | Prioritize fixes and improvements from real user signals |
| **Support** | Align messaging with what users are actually saying |
| **Leadership** | One-page health check without drowning in raw reviews |

---

## 🏗️ What Must Be Built

| # | Requirement |
|---|---|
| 1 | Import reviews from the **last 8–12 weeks** (fields: rating, title, text, date — whatever the export provides) |
| 2 | Group reviews into **at most 5 themes** (e.g. onboarding, KYC, payments, statements, withdrawals) |
| 3 | Generate a weekly one-page note with **top 3 themes**, **3 user quotes**, and **3 action ideas** |
| 4 | Draft an email with the note to the user or an alias |

---

## 🗂️ Key Constraints & Notes

- Themes should be chosen to **fit the product** (the examples are illustrative, not fixed).
- User quotes must be **verbatim** — no paraphrasing or invented wording.
- Action ideas must be **grounded in the themes** — concrete and actionable.
- The system must operate within the **platform''s usage rules** for App Store / Play Store data.
- Integration surfaces are **Google Docs** and **Gmail** (no custom credential or REST layer needed by the developer).
