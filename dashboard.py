# ============================================================
# MEDOPS AI - HOSPITAL OPERATIONS DASHBOARD
# ============================================================
# Streamlit front end for the MedOps AI FastAPI analytics API.
#
# Dashboard sections:
# 1. Key performance indicators
# 2. Ticket volume by category
# 3. Priority distribution
# 4. Daily ticket volume
# 5. Tickets by assigned department
# 6. SLA monitoring status
# ============================================================

import os

import altair as alt
import pandas as pd
import requests
import streamlit as st


# ------------------------------------------------------------
# 1. PAGE CONFIGURATION
# ------------------------------------------------------------

st.set_page_config(
    page_title="MedOps AI | Hospital Operations",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Use an environment variable for deployment, with localhost as
# the default when running the backend on the same computer.
API_URL = os.getenv(
    "MEDOPS_API_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


# ------------------------------------------------------------
# 2. CUSTOM NAVY THEME AND STYLING
# ------------------------------------------------------------

# The palette keeps navy as the main colour and uses:
# cyan/blue for information, red for High, amber for Medium,
# and green/teal for Low priority.
st.markdown(
    """
    <style>
    :root {
        --page: #071426;
        --sidebar: #0b1d35;
        --panel: #102641;
        --panel-soft: #142e4d;
        --border: #234363;
        --text: #f3f7fc;
        --muted: #a9bdd2;
        --blue: #38a8f5;
        --cyan: #42c7d5;
        --red: #f06464;
        --amber: #f5b544;
        --green: #31c48d;
        --purple: #8b7cf6;
    }

    /* Main application background and default text */
    .stApp {
        background:
            radial-gradient(ellipse at 75% 0%, #102b4b 0%, transparent 42%),
            var(--page);
        color: var(--text);
    }

    /* Main content spacing */
    .block-container {
        max-width: 1600px;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d2340 0%, #09182c 100%);
        border-right: 1px solid var(--border);
    }

    [data-testid="stSidebar"] * {
        color: var(--text);
    }

    [data-testid="stSidebar"] .stCaption {
        color: var(--muted);
    }

    /* Hide Streamlit's default top toolbar and footer for a cleaner app */
    [data-testid="stHeader"] {
        background: rgba(7, 20, 38, 0.96);
    }

    #MainMenu, footer {
        visibility: hidden;
    }

    /* Headings and supporting text */
    h1, h2, h3 {
        color: var(--text) !important;
        letter-spacing: -0.025em;
    }

    p, label, [data-testid="stMarkdownContainer"] {
        color: var(--text);
    }

    .dashboard-subtitle {
        color: var(--muted);
        font-size: 1rem;
        margin-top: -0.45rem;
    }

    .eyebrow {
        color: var(--cyan);
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.72rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }

    /* Reusable chart and information panels */
    .panel {
        background: linear-gradient(145deg, #122b48 0%, #0e223b 100%);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 1.15rem 1.25rem;
        min-height: 100%;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
    }

    .panel-title {
        color: var(--text);
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 0.85rem;
    }

    /* KPI cards */
    .kpi-card {
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, #183653 0%, #102640 100%);
        border: 1px solid #2a4d70;
        border-radius: 16px;
        padding: 1.05rem 1.15rem;
        min-height: 126px;
        box-shadow: 0 8px 22px rgba(0, 0, 0, 0.15);
    }

    .kpi-card::after {
        content: "";
        position: absolute;
        width: 130px;
        height: 65px;
        right: -24px;
        bottom: -34px;
        border-radius: 50%;
        background: var(--glow);
        filter: blur(24px);
        opacity: 0.32;
    }

    .kpi-top {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        color: #d8e6f5;
        font-size: 0.88rem;
        font-weight: 600;
    }

    .kpi-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 34px;
        height: 34px;
        border-radius: 50%;
        background: var(--accent);
        color: #071426;
        font-weight: 900;
        font-size: 1.05rem;
    }

    .kpi-value {
        color: #ffffff;
        font-size: 2rem;
        line-height: 1.15;
        font-weight: 750;
        margin: 0.55rem 0 0 2.85rem;
    }

    .period-line {
        color: var(--muted);
        font-size: 0.86rem;
        padding: 0.9rem 0 0.75rem 0;
        border-bottom: 1px solid var(--border);
        margin-bottom: 1.2rem;
    }

    /* SLA notice */
    .sla-notice {
        background: linear-gradient(100deg, #10375b 0%, #123253 100%);
        border: 1px solid #269fe5;
        border-left: 5px solid #42c7f5;
        border-radius: 14px;
        padding: 1rem 1.2rem;
        color: #eaf5ff;
    }

    .sla-heading {
        font-size: 1rem;
        font-weight: 750;
        margin-bottom: 0.25rem;
    }

    .sla-copy {
        color: #c7dced;
        font-size: 0.88rem;
        line-height: 1.5;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #1266ae, #1687ce);
        color: white;
        border: 1px solid #258fd2;
        border-radius: 10px;
        font-weight: 650;
        min-height: 2.6rem;
    }

    .stButton > button:hover {
        background: #1b91d8;
        border-color: #5bc4f4;
        color: white;
    }

    /* Dataframe/table styling */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
    }

    /* Dividers */
    hr {
        border-color: var(--border);
    }

    /* Make native Streamlit chart containers match the navy theme */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(145deg, #122b48, #0e223b);
    border: 1px solid #234363;
    border-radius: 16px;
    padding: 16px;
}
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# 3. FETCH ANALYTICS FROM FASTAPI
# ------------------------------------------------------------

@st.cache_data(ttl=30, show_spinner=False)
def fetch_analytics():
    """
    Request the aggregated ticket analytics from FastAPI.

    The backend owns the analytics calculations. Streamlit only
    displays the returned data; it does not recalculate totals.
    The short cache reduces repeated requests during page reruns.
    """
    response = requests.get(f"{API_URL}/analytics", timeout=15)
    response.raise_for_status()
    return response.json()


# ------------------------------------------------------------
# 4. SIDEBAR
# ------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div style="text-align:center; padding: 1.1rem 0 1.4rem 0;">
            <div style="font-size:2.8rem;">🏥</div>
            <div style="font-size:1.55rem; font-weight:800;">MedOps AI</div>
            <div style="font-size:0.82rem; color:#a9bdd2;">
                Hospital Operations Analytics
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    st.markdown("### ▦  Dashboard")
    st.caption("Ticket analytics and operational insights")

    st.divider()

    st.markdown("**Data source**")
    st.caption(f"`{API_URL}/analytics`")

    # Clear the cached API response before rerunning the page.
    if st.button("↻  Refresh dashboard", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        """
        <div style="
            margin-top: 3rem;
            padding: 1rem 0.2rem;
            text-align: center;
            color: #8fb8dc;
            border-top: 1px solid #234363;
        ">
            <div style="font-size:2rem;">〰</div>
            <i>Smarter Operations.<br>Better Care.</i>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# 5. LOAD DATA AND HANDLE API ERRORS
# ------------------------------------------------------------

try:
    analytics = fetch_analytics()

except requests.exceptions.ConnectionError:
    st.error(
        "The dashboard cannot connect to the FastAPI backend. "
        "Start the backend with: python -m uvicorn app.main:app --reload"
    )
    st.stop()

except requests.exceptions.Timeout:
    st.error("The analytics API took too long to respond. Please refresh.")
    st.stop()

except requests.exceptions.HTTPError as error:
    st.error(f"The analytics API returned an HTTP error: {error}")
    st.stop()

except requests.exceptions.RequestException as error:
    st.error(f"Unable to retrieve analytics: {error}")
    st.stop()

except ValueError:
    st.error("The analytics API returned invalid JSON.")
    st.stop()


# Extract fields from the API response. Defaults protect the page
# if an optional analytics field is missing.
total = analytics.get("total_tickets", 0)
categories = analytics.get("by_category", {})
priorities = analytics.get("by_priority", {})
departments = analytics.get("by_department", {})
daily_data = analytics.get("by_day", [])
rates = analytics.get("rates", {})
date_range = analytics.get("date_range", {})

if total == 0:
    st.info("No ticket records are available yet.")
    st.stop()


# ------------------------------------------------------------
# 6. DASHBOARD HEADER
# ------------------------------------------------------------

header_left, header_right = st.columns([5, 1])

with header_left:
    st.markdown('<div class="eyebrow">MEDOPS AI / ANALYTICS</div>',
                unsafe_allow_html=True)
    st.title("Hospital Operations Dashboard")
    st.markdown(
        '<div class="dashboard-subtitle">'
        'Monitor hospital support requests, ticket priorities, '
        'and operational trends.'
        '</div>',
        unsafe_allow_html=True,
    )

with header_right:
    st.write("")
    if st.button("↻  Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ------------------------------------------------------------
# 7. KEY PERFORMANCE INDICATORS
# ------------------------------------------------------------

# Each KPI uses a distinct semantic colour:
# blue = total volume, red = high, amber = medium, green = low.
high = priorities.get("High", 0)
medium = priorities.get("Medium", 0)
low = priorities.get("Low", 0)

kpi_columns = st.columns(4)

kpis = [
    ("▣", "Total Tickets", total, "#38a8f5", "#1b83d1"),
    ("!", "High Priority", high, "#f06464", "#f06464"),
    ("–", "Medium Priority", medium, "#f5b544", "#f5b544"),
    ("✓", "Low Priority", low, "#31c48d", "#31c48d"),
]

for column, (symbol, label, value, accent, glow) in zip(kpi_columns, kpis):
    with column:
        st.markdown(
            f"""
            <div class="kpi-card" style="--accent:{accent}; --glow:{glow};">
                <div class="kpi-top">
                    <span class="kpi-icon">{symbol}</span>
                    <span>{label}</span>
                </div>
                <div class="kpi-value">{value:,}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# Show the period covered by the analytics response.
first_date = date_range.get("first") or "N/A"
last_date = date_range.get("last") or "N/A"

st.markdown(
    f'<div class="period-line">▦ &nbsp; Reporting period: '
    f'{first_date} to {last_date}</div>',
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# 8. TICKET VOLUME BY CATEGORY
# ------------------------------------------------------------

# Convert category counts into a DataFrame for Altair.
category_df = pd.DataFrame(
    [
        {"Category": name, "Tickets": count}
        for name, count in categories.items()
    ]
)

# Assign a distinct colour to each ticket category.
category_colours = {
    "IT & Medical Tech": "#269df4",
    "HR": "#8b7cf6",
    "Operations": "#28b7a4",
    "Finance": "#f59e36",
}

# ------------------------------------------------------------
# 9. PRIORITY DISTRIBUTION
# ------------------------------------------------------------

# Define the priority order and corresponding colours.
priority_order = ["High", "Medium", "Low"]

priority_colours = {
    "High": "#f06464",
    "Medium": "#f5b544",
    "Low": "#31c48d",
}

# Prepare priority data.
priority_df = pd.DataFrame({
    "Priority": priority_order,
    "Tickets": [
        priorities.get(item, 0)
        for item in priority_order
    ],
})

# Create the priority bar chart BEFORE displaying it.
priority_chart = (
    alt.Chart(priority_df)
    .mark_bar(
        cornerRadiusTopLeft=5,
        cornerRadiusTopRight=5,
    )
    .encode(
        x=alt.X(
            "Priority:N",
            sort=priority_order,
            axis=alt.Axis(
                title=None,
                labelColor="#dce9f7",
                labelFontSize=12,
                ticks=False,
                domainColor="#49627e",
            ),
        ),
        y=alt.Y(
            "Tickets:Q",
            axis=alt.Axis(
                title=None,
                labelColor="#a9bdd2",
                gridColor="#29435f",
                tickMinStep=1,
            ),
        ),
        color=alt.Color(
            "Priority:N",
            scale=alt.Scale(
                domain=priority_order,
                range=[
                    priority_colours[item]
                    for item in priority_order
                ],
            ),
            legend=None,
        ),
        tooltip=["Priority:N", "Tickets:Q"],
    )
    .properties(height=245)
    .configure_view(stroke=None)
    .configure(background="transparent")
)

# ------------------------------------------------------------
# CREATE THE CATEGORY DOUGHNUT CHART
# ------------------------------------------------------------

if not category_df.empty:

    # Create the doughnut chart.
    category_donut = (
        alt.Chart(category_df)
        .mark_arc(
            innerRadius=58,
            outerRadius=105,
            cornerRadius=4,
        )
        .encode(
            theta=alt.Theta("Tickets:Q", stack=True),
            color=alt.Color(
                "Category:N",
                scale=alt.Scale(
                    domain=list(category_colours.keys()),
                    range=list(category_colours.values()),
                ),
                legend=alt.Legend(
                    title=None,
                    orient="right",
                    labelColor="#dce9f7",
                    labelFontSize=12,
                    symbolSize=120,
                ),
            ),
            tooltip=["Category:N", "Tickets:Q"],
        )
    )

    # Create the total ticket count displayed in the centre.
    centre_text = (
        alt.Chart(
            pd.DataFrame({"label": [f"{total}\nTotal"]})
        )
        .mark_text(
            color="#f3f7fc",
            fontSize=18,
            fontWeight="bold",
            lineBreak="\n",
        )
        .encode(text="label:N")
    )

    # Combine the doughnut and centre text into one chart.
    category_chart = (
        alt.layer(category_donut, centre_text)
        .properties(height=245)
        .configure_view(stroke=None)
        .configure(background="transparent")
    )

# ------------------------------------------------------------
# DISPLAY CATEGORY AND PRIORITY CHARTS
# ------------------------------------------------------------

# Display both charts side by side in equal-width columns.
left, right = st.columns(2)

# CATEGORY PANEL
with left:
    with st.container(border=True):
        st.markdown("### Ticket Volume by Category")

        if not category_df.empty:
            st.altair_chart(
                category_chart,
                use_container_width=True,
            )
        else:
            st.info("Category analytics are not available.")

# PRIORITY PANEL
with right:
    with st.container(border=True):
        st.markdown("### Priority Distribution")

        st.altair_chart(
            priority_chart,
            use_container_width=True,
        )

        # Display the percentage of tickets classified as High.
        high_share = rates.get("high_priority_share", 0) * 100

        st.metric(
            "High Priority Share",
            f"{high_share:.1f}%",
        )

st.write("")

# ------------------------------------------------------------
# 10. DAILY TICKET VOLUME TREND
# ------------------------------------------------------------

# The API returns only dates with tickets. Reindexing adds dates
# with zero tickets so the line chart displays a continuous timeline.
st.markdown(
    '<div class="panel-title">Daily Ticket Volume</div>',
    unsafe_allow_html=True,
)

if daily_data:
    daily_df = pd.DataFrame(daily_data)
    daily_df["date"] = pd.to_datetime(daily_df["date"])

    all_dates = pd.date_range(
        start=daily_df["date"].min(),
        end=daily_df["date"].max(),
        freq="D",
    )

    daily_df = (
        daily_df.set_index("date")
        .reindex(all_dates, fill_value=0)
        .rename_axis("date")
        .reset_index()
    )

    daily_df = daily_df.rename(columns={"count": "Tickets"})

    daily_chart = (
        alt.Chart(daily_df)
        .mark_line(
            color="#38a8f5",
            strokeWidth=3,
            point=alt.OverlayMarkDef(
                filled=True,
                fill="#42c7f5",
                size=85,
            ),
        )
        .encode(
            x=alt.X(
                "date:T",
                axis=alt.Axis(
                    title=None,
                    labelColor="#dce9f7",
                    labelFontSize=11,
                    labelAngle=0,
                    format="%b %d",
                    tickCount=8,
                    labelOverlap=True,
                    gridColor="#203a56",
                ),
            ),
            y=alt.Y(
                "Tickets:Q",
                axis=alt.Axis(
                    title=None,
                    labelColor="#a9bdd2",
                    gridColor="#29435f",
                    tickMinStep=1,
                ),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("Tickets:Q", title="Tickets"),
            ],
        )
        .properties(height=245)
        .configure_view(stroke=None)
        .configure(background="transparent")
    )

    st.altair_chart(daily_chart, use_container_width=True)

    st.caption(
        f"Average tickets per day: "
        f"{rates.get('tickets_per_day', 0):.2f}"
    )
else:
    st.info("Daily ticket history is not available.")


# ------------------------------------------------------------
# 11. TICKETS BY ASSIGNED DEPARTMENT
# ------------------------------------------------------------

st.markdown(
    '<div class="panel-title">Tickets by Assigned Department</div>',
    unsafe_allow_html=True,
)

department_df = pd.DataFrame(
    [{"Department": name, "Tickets": count}
     for name, count in departments.items()]
)

if not department_df.empty:
    department_df = department_df.sort_values("Tickets", ascending=True)

    department_chart = (
        alt.Chart(department_df)
        .mark_bar(color="#647ee8", cornerRadiusEnd=4)
        .encode(
            x=alt.X(
                "Tickets:Q",
                axis=alt.Axis(
                    title=None,
                    labelColor="#a9bdd2",
                    gridColor="#29435f",
                    tickMinStep=1,
                ),
            ),
            y=alt.Y(
                "Department:N",
                sort="-x",
                axis=alt.Axis(
                    title=None,
                    labelColor="#dce9f7",
                    labelLimit=280,
                    labelFontSize=11,
                ),
            ),
            tooltip=["Department:N", "Tickets:Q"],
        )
        .properties(height=max(230, len(department_df) * 34))
        .configure_view(stroke=None)
        .configure(background="transparent")
    )

    st.altair_chart(department_chart, use_container_width=True)
else:
    st.info("Department analytics are not available.")


st.write("")


# ------------------------------------------------------------
# 12. SERVICE LEVEL AGREEMENT (SLA) MONITORING
# ------------------------------------------------------------

# SLA performance must not be estimated from ticket creation dates.
# The current API does not contain actual first-response timestamps
# or team-approved response-time targets, so no SLA rate is shown.
st.markdown(
    """
    <div class="sla-notice">
        <div class="sla-heading">
            ⓘ &nbsp; Service Level Agreement (SLA) Monitoring
        </div>
        <div class="sla-copy">
            SLA reporting is pending. The current analytics service
            tracks ticket creation dates, categories, and priorities.
            It does not yet record first-response times or approved
            response-time targets. SLA performance will be displayed
            once these fields and targets are agreed by the project team.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# 13. FOOTER
# ------------------------------------------------------------

st.markdown(
    """
    <div style="
        text-align:center;
        color:#7894b1;
        font-size:0.78rem;
        padding:1.5rem 0 0.5rem 0;
    ">
        MedOps AI &nbsp;•&nbsp; Hospital Operations Analytics
    </div>
    """,
    unsafe_allow_html=True,
)
