import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from mock_data import trend_data, sentiment_data, category_data, mock_reviews, action_ideas

# Must be the first Streamlit command
st.set_page_config(
    page_title="FeedbackPulse",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS to try and mimic the dark theme and glassmorphism styling
st.markdown("""
    <style>
    .reportview-container {
        background: #090d16;
    }
    .stApp {
        background: #090d16;
        color: #e2e8f0;
    }
    header {visibility: hidden;}
    .css-1d391kg, .css-1dp5vir, .css-18ni7ap, .css-1vq4p4l, .css-163ttcj {
        background-color: #0d1322 !important;
    }
    .metric-card {
        background-color: rgba(19, 28, 49, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.06);
        padding: 1.5rem;
        border-radius: 1rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .metric-title {
        color: #94a3b8;
        font-size: 0.875rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.5rem;
    }
    .metric-value {
        font-size: 2.25rem;
        font-weight: 800;
        color: #ffffff;
    }
    .metric-delta {
        font-size: 0.875rem;
        color: #34d399;
        font-weight: 500;
    }
    .metric-sub {
        font-size: 0.75rem;
        color: #64748b;
        margin-top: 0.5rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar Navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 📈 FeedbackPulse `v2.4`")
    st.caption("Fintech Intelligence")
    
    st.markdown("---")
    st.markdown("🟢 **PhonePe India**")
    st.caption("iOS • Play Store")
    st.markdown("---")
    
    view = st.radio(
        "Navigation",
        ["Analytics", "Reviews Feed", "Categories & Themes", "Action Ideation", "Weekly Reporting"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.info("🔄 Sync: 8m ago (99.8% parsed)")
    st.markdown("**User:** Aayush Patel (Lead PM)")

# ---------------------------------------------------------------------------
# Header (Search & Filters)
# ---------------------------------------------------------------------------

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    search_query = st.text_input("Global Search", placeholder="Search reviews, keywords...", label_visibility="collapsed")
with col2:
    date_range = st.selectbox("Date Range", ["Last 12 Weeks", "Last 30 Days", "Last 7 Days", "Year to Date"], label_visibility="collapsed")
with col3:
    st.button("🔄 Sync Stores", use_container_width=True, type="primary")

st.markdown("---")

# ---------------------------------------------------------------------------
# View 1: Analytics
# ---------------------------------------------------------------------------
if view == "Analytics":
    st.title("Review Analytics Overview")
    st.caption("Cross-platform feedback synthesis for PhonePe India iOS & Google Play Store.")
    
    # KPI Metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-title">Total Reviews</div>
            <div class="metric-value">148,290</div>
            <div class="metric-delta">↑ +12.4%</div>
            <div class="metric-sub">vs. previous 12 weeks</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-title">Average Rating</div>
            <div class="metric-value">4.32 ★</div>
            <div class="metric-delta">↑ +0.18</div>
            <div class="metric-sub">iOS: 4.45 | Play: 4.28</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-title">Sentiment Balance</div>
            <div class="metric-value">73% <span style='font-size:1rem; color:#f43f5e;'>/ 19%</span></div>
            <div class="metric-delta">Pos / Neg</div>
            <div class="metric-sub">8% Neutral</div>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-title">Top Trending Theme</div>
            <div class="metric-value" style="font-size: 1.8rem;">UPI Payments</div>
            <div class="metric-delta" style="color:#f43f5e;">High Surge</div>
            <div class="metric-sub">42% of all complaints</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Charts
    chart_col1, chart_col2 = st.columns([2, 1])
    
    with chart_col1:
        st.subheader("Review Volume & Average Rating Trajectory")
        fig_line = go.Figure()
        # Add Volume Bar
        fig_line.add_trace(go.Bar(
            x=trend_data['week'],
            y=trend_data['volume'],
            name='Volume',
            marker_color='#6366f1'
        ))
        # Add Rating Line on secondary y-axis
        fig_line.add_trace(go.Scatter(
            x=trend_data['week'],
            y=trend_data['rating'],
            name='Avg Rating',
            yaxis='y2',
            mode='lines+markers',
            line=dict(color='#fbbf24', width=3),
            marker=dict(size=8)
        ))
        fig_line.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e2e8f0'),
            yaxis=dict(title='Volume'),
            yaxis2=dict(title='Avg Rating', overlaying='y', side='right', range=[1, 5]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_line, use_container_width=True)

    with chart_col2:
        st.subheader("Sentiment by Day")
        fig_bar = px.bar(
            sentiment_data, x="day", y=["positive", "neutral", "negative"],
            color_discrete_map={
                "positive": "#34d399",
                "neutral": "#fbbf24",
                "negative": "#fb7185"
            },
            barmode='stack'
        )
        fig_bar.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e2e8f0'),
            legend_title_text='',
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        
    st.info("🤖 **Pulse AI Alert:** 48 new reviews flagged UPI Autopay confusion since Friday 18:00 IST.")

# ---------------------------------------------------------------------------
# View 2: Reviews Feed
# ---------------------------------------------------------------------------
elif view == "Reviews Feed":
    st.title("Raw Reviews Feed")
    st.caption("Real-time user feedback with automated sentiment scoring and category classification.")
    
    col1, col2, col3, col4 = st.columns(4)
    filter_platform = col1.selectbox("Platform", ["All", "App Store", "Play Store"])
    filter_rating = col2.selectbox("Rating", ["All", "5", "4", "3", "2", "1"])
    filter_category = col3.selectbox("Category", ["All", "Payments", "Onboarding", "KYC", "Statements"])
    filter_sentiment = col4.selectbox("Sentiment", ["All", "Positive", "Neutral", "Negative"])
    
    filtered_df = mock_reviews.copy()
    if filter_platform != "All": filtered_df = filtered_df[filtered_df['platform'] == filter_platform]
    if filter_rating != "All": filtered_df = filtered_df[filtered_df['rating'].astype(str) == filter_rating]
    if filter_category != "All": filtered_df = filtered_df[filtered_df['category'] == filter_category]
    if filter_sentiment != "All": filtered_df = filtered_df[filtered_df['sentiment'] == filter_sentiment]
    
    st.markdown(f"**Showing {len(filtered_df)} reviews**")
    
    st.dataframe(
        filtered_df[['author', 'platform', 'rating', 'category', 'sentiment', 'text']],
        use_container_width=True,
        hide_index=True
    )

# ---------------------------------------------------------------------------
# View 3: Categories & Themes
# ---------------------------------------------------------------------------
elif view == "Categories & Themes":
    st.title("Thematic Category Analysis")
    
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.subheader("Volume Share")
        fig_pie = px.pie(
            category_data, values='value', names='name', hole=0.7,
            color='name',
            color_discrete_map={
                "Payments": "#6366f1",
                "KYC": "#22d3ee",
                "Onboarding": "#fbbf24",
                "Statements": "#fb7185"
            }
        )
        fig_pie.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e2e8f0'),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with col2:
        st.subheader("Category Health")
        
        st.markdown("#### 💳 Payments & UPI Transfers")
        st.caption("62,280 reviews • Trending Negatively (-4.2%)")
        st.progress(68, text="Satisfaction Score: 68%")
        st.error("Top issue: Bank timeout during merchant QR")
        
        st.markdown("#### 🛡️ KYC & Aadhaar Verification")
        st.caption("32,620 reviews • Trending Positively (+8.1%)")
        st.progress(84, text="Satisfaction Score: 84%")
        st.success("Facial liveness verification speed improved")
        
        st.markdown("#### 👤 Onboarding & SIM Binding")
        st.caption("26,690 reviews • Stable Positive (+3.5%)")
        st.progress(79, text="Satisfaction Score: 79%")
        
        st.markdown("#### 📄 Statements & Tax Passbook")
        st.caption("26,700 reviews • Trending Negatively (-1.2%)")
        st.progress(72, text="Satisfaction Score: 72%")
        st.warning("Tax statement download fails on iOS 17")

# ---------------------------------------------------------------------------
# View 4: Action Ideation
# ---------------------------------------------------------------------------
elif view == "Action Ideation":
    st.title("Action Ideation 🤖")
    st.caption("Product feature proposals and fixes automatically synthesized from feedback clusters using Groq LLM.")
    
    col1, col2 = st.columns(2)
    cols = [col1, col2]
    
    for idx, idea in enumerate(action_ideas):
        with cols[idx % 2]:
            with st.container():
                st.markdown(f"### {idea['title']}")
                
                if idea['impact'] == 'High':
                    st.error("Impact: High")
                elif idea['impact'] == 'Medium':
                    st.warning("Impact: Medium")
                else:
                    st.info("Impact: Low")
                    
                st.markdown(idea['description'])
                st.caption(f"Category: **{idea['category']}** • Backed by {idea['reviews']} reviews")
                st.button("👍 Approve", key=f"app_{idx}")
                st.markdown("---")

# ---------------------------------------------------------------------------
# View 5: Weekly Reporting
# ---------------------------------------------------------------------------
elif view == "Weekly Reporting":
    st.title("Weekly Reporting")
    
    col1, col2, col3 = st.columns([1,1,6])
    col1.button("📄 Export PDF")
    col2.button("✉️ Draft Gmail")
    
    st.markdown("---")
    
    st.markdown("""
    ## Weekly Pulse: Payment Failures and Unmatched Review Surge
    *Week ending 2026-09-06*
    
    ### Executive Summary
    This week, payment issues dominated feedback with 76 reviews, while 49 unmatched reports suggest a new pattern emerging. The overall sentiment remains largely positive (73%), but the surge in critical feedback regarding UPI mandates warrants immediate attention.
    
    ### Top Themes
    * **Payments (59%):** Heavy volume centered around Autopay failures and merchant QR timeouts.
    * **Onboarding (2%):** Minor friction around SIM binding for dual-SIM devices.
    * **KYC (1%):** Overall highly positive feedback on video verification speeds.
    
    ### Polished Action Items
    1. **Smart Retry:** Audit the 76 payment reviews to identify the primary failure cause and implement a specific retry mechanism.
    2. **Progress Indicator:** Analyze the onboarding reviews to pinpoint the exact drop-off step and add a progress indicator.
    3. **Emerging Issue Audit:** Review the 49 unmatched reviews for emerging account-blocking or trading issues.
    
    ### Raw Voices
    > "Money deducted from my account but the merchant says they did not receive it. UPI is completely broken since the last update. Fix this ASAP!"
    > — Rahul Sharma (Play Store, 1 Star)
    """)
