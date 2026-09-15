import pandas as pd

# ---------------------------------------------------------------------------
# Analytics Data
# ---------------------------------------------------------------------------

trend_data = pd.DataFrame([
    {"week": "W1", "volume": 800, "rating": 4.1},
    {"week": "W2", "volume": 950, "rating": 4.2},
    {"week": "W3", "volume": 1100, "rating": 4.3},
    {"week": "W4", "volume": 1050, "rating": 4.3},
    {"week": "W5", "volume": 1200, "rating": 4.4},
    {"week": "W6", "volume": 1300, "rating": 4.4},
    {"week": "W7", "volume": 1450, "rating": 4.5},
    {"week": "W8", "volume": 2200, "rating": 3.8}, # Drop after update
    {"week": "W9", "volume": 1800, "rating": 3.9},
    {"week": "W10", "volume": 1500, "rating": 4.1},
    {"week": "W11", "volume": 1400, "rating": 4.2},
    {"week": "W12", "volume": 1250, "rating": 4.32},
])

sentiment_data = pd.DataFrame([
    {"day": "Mon", "positive": 65, "neutral": 15, "negative": 20},
    {"day": "Tue", "positive": 70, "neutral": 10, "negative": 20},
    {"day": "Wed", "positive": 68, "neutral": 12, "negative": 20},
    {"day": "Thu", "positive": 72, "neutral": 10, "negative": 18},
    {"day": "Fri", "positive": 40, "neutral": 10, "negative": 50},
    {"day": "Sat", "positive": 80, "neutral": 10, "negative": 10},
    {"day": "Sun", "positive": 85, "neutral": 5, "negative": 10},
])

category_data = pd.DataFrame([
    {"name": "Payments", "value": 42},
    {"name": "KYC", "value": 22},
    {"name": "Onboarding", "value": 18},
    {"name": "Statements", "value": 18},
])

# ---------------------------------------------------------------------------
# Reviews Data
# ---------------------------------------------------------------------------

mock_reviews = pd.DataFrame([
    {
        "id": 1,
        "author": "Rahul Sharma",
        "platform": "Play Store",
        "rating": 1,
        "date": "Today, 14:32",
        "category": "Payments",
        "sentiment": "Negative",
        "text": "Money deducted from my account but the merchant says they did not receive it. UPI is completely broken since the last update. Fix this ASAP!"
    },
    {
        "id": 2,
        "author": "Priya Patel",
        "platform": "App Store",
        "rating": 5,
        "date": "Yesterday, 09:15",
        "category": "Onboarding",
        "sentiment": "Positive",
        "text": "Very smooth onboarding experience. Loved how quickly it detected my SIM and set up the bank account. Good job team PhonePe."
    },
    {
        "id": 3,
        "author": "Amit Kumar",
        "platform": "Play Store",
        "rating": 3,
        "date": "2 days ago",
        "category": "Statements",
        "sentiment": "Neutral",
        "text": "The app works fine for payments, but finding the tax statement for the last financial year is very confusing. Please make the UI simpler."
    },
    {
        "id": 4,
        "author": "Sneha Reddy",
        "platform": "App Store",
        "rating": 4,
        "date": "3 days ago",
        "category": "KYC",
        "sentiment": "Positive",
        "text": "The video KYC process was actually surprisingly fast. I was verified within 5 minutes. Deducting one star because the agent was a bit rude."
    },
    {
        "id": 5,
        "author": "Vikram Singh",
        "platform": "Play Store",
        "rating": 2,
        "date": "4 days ago",
        "category": "Payments",
        "sentiment": "Negative",
        "text": "Autopay for my mutual fund SIP failed for the second month in a row. It says mandate rejected by bank, but my bank says everything is fine."
    }
])

# ---------------------------------------------------------------------------
# Ideation Data
# ---------------------------------------------------------------------------

action_ideas = [
    {
        "title": "Implement Smart Retry for UPI Failures",
        "description": "Analyze the 76 payment reviews to identify the primary failure cause (merchant timeout vs bank rejection) and implement specific error messaging with an immediate retry button.",
        "impact": "High",
        "reviews": 76,
        "category": "Payments"
    },
    {
        "title": "Add Progress Indicator for Onboarding",
        "description": "Review the recent onboarding feedback to pinpoint the exact drop-off step (often SIM binding). Add a clear 3-step progress indicator to set user expectations.",
        "impact": "Medium",
        "reviews": 12,
        "category": "Onboarding"
    },
    {
        "title": "Investigate Autopay Mandate Rejections",
        "description": "Audit the 48 new reviews complaining about SIP and bill payment mandates failing. Check the NPCI settlement logs for the recent weekend period.",
        "impact": "High",
        "reviews": 48,
        "category": "Payments"
    },
    {
        "title": "Redesign Statements Dashboard",
        "description": "Users are struggling to find the tax statement. Move the 'Download Tax Report' button to the top level of the History tab.",
        "impact": "Low",
        "reviews": 8,
        "category": "Statements"
    }
]
