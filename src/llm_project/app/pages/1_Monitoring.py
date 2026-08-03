"""Monitoring dashboard (rubric: user feedback collected + dashboard with >=5 charts).

Reads conversations/feedback logged by the main chat page (see db/client.py) from
Postgres and renders KPIs plus charts. Colors follow a fixed categorical hue order
for identity (mode, retrieval method) and a single blue hue for magnitude
(counts over time, response time, citation frequency), with feedback using the
good/critical status pair since up/down votes are a state, not a category.
"""

import altair as alt
import pandas as pd
import streamlit as st

from llm_project.analytics.tools import ALLOWED_TEST_CODES
from llm_project.db.client import get_conversations_df, get_feedback_df, get_source_files_df

st.set_page_config(page_title="Monitoring - ScanFlow AI", layout="wide")

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE = "#2a78d6"
STATUS_GOOD = "#0ca30c"
STATUS_CRITICAL = "#d03b3b"

st.title("Monitoring")
st.caption("Usage and feedback for ScanFlow AI, logged to Postgres on every interaction.")

try:
    conversations = get_conversations_df()
    feedback = get_feedback_df()
except Exception as e:
    st.error(f"Could not reach the monitoring database: {e}")
    st.stop()

if conversations.empty:
    st.info("No conversations logged yet — ask the app a question first, then reload this page.")
    st.stop()

conversations["created_at"] = pd.to_datetime(conversations["created_at"])
if not feedback.empty:
    feedback["created_at"] = pd.to_datetime(feedback["created_at"])

n_conversations = len(conversations)
n_feedback = len(feedback)
up_rate = (feedback["rating"] == 1).mean() if n_feedback else None
avg_response_time = conversations["response_time_seconds"].mean()
total_cost = conversations["estimated_cost"].sum() if "estimated_cost" in conversations else None

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Conversations", n_conversations)
col2.metric("Feedback votes", n_feedback)
col3.metric("Positive feedback rate", f"{up_rate:.0%}" if up_rate is not None else "n/a")
col4.metric("Avg response time", f"{avg_response_time:.1f}s")
col5.metric("Total LLM cost (USD)", f"${total_cost:.4f}" if total_cost else "n/a")

st.divider()

st.subheader("Conversations per day")
daily = (
    conversations.assign(day=conversations["created_at"].dt.date)
    .groupby("day")
    .size()
    .reset_index(name="count")
)
chart = (
    alt.Chart(daily)
    .mark_line(point=True, color=BLUE, strokeWidth=2)
    .encode(x=alt.X("day:T", title=None), y=alt.Y("count:Q", title="Conversations"), tooltip=["day:T", "count:Q"])
)
st.altair_chart(chart, use_container_width=True)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Interactions by mode")
    st.caption("agent = Ask ScanFlow (tool-calling); the other two are direct, tool-only lookups.")
    mode_counts = conversations["mode"].value_counts().reset_index()
    mode_counts.columns = ["mode", "count"]
    mode_domain = sorted(mode_counts["mode"].unique().tolist())
    chart = (
        alt.Chart(mode_counts)
        .mark_bar(size=50)
        .encode(
            x=alt.X("mode:N", title=None, sort="-y"),
            y=alt.Y("count:Q", title="Interactions"),
            color=alt.Color("mode:N", scale=alt.Scale(domain=mode_domain, range=CATEGORICAL), legend=None),
            tooltip=["mode", "count"],
        )
    )
    st.altair_chart(chart, use_container_width=True)

with col_b:
    st.subheader("Questions by diagnostic test")
    st.caption("Inferred by matching test codes mentioned in the logged question text.")
    pattern = "|".join(sorted(ALLOWED_TEST_CODES, key=len, reverse=True)).replace("_", "[ _]")
    mentions = conversations["question"].str.upper().str.extractall(f"({pattern})")
    if not mentions.empty:
        test_counts = mentions[0].value_counts().reset_index()
        test_counts.columns = ["test", "count"]
        chart = (
            alt.Chart(test_counts)
            .mark_bar(size=35)
            .encode(
                x=alt.X("test:N", title=None, sort="-y"),
                y=alt.Y("count:Q", title="Questions"),
                color=alt.Color("test:N", scale=alt.Scale(domain=sorted(ALLOWED_TEST_CODES), range=CATEGORICAL), legend=None),
                tooltip=["test", "count"],
            )
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No diagnostic test mentioned in any logged question yet.")

st.subheader("Response time distribution")
chart = (
    alt.Chart(conversations)
    .mark_bar(color=BLUE)
    .encode(
        x=alt.X("response_time_seconds:Q", bin=alt.Bin(maxbins=20), title="Response time (s)"),
        y=alt.Y("count():Q", title="Conversations"),
    )
)
st.altair_chart(chart, use_container_width=True)

col_c, col_d = st.columns(2)

with col_c:
    st.subheader("Feedback")
    if n_feedback:
        fb_counts = feedback["rating"].map({1: "positive", -1: "negative"}).value_counts().reset_index()
        fb_counts.columns = ["rating", "count"]
        chart = (
            alt.Chart(fb_counts)
            .mark_bar(size=50)
            .encode(
                x=alt.X("rating:N", title=None, sort=["positive", "negative"]),
                y=alt.Y("count:Q", title="Votes"),
                color=alt.Color(
                    "rating:N",
                    scale=alt.Scale(domain=["positive", "negative"], range=[STATUS_GOOD, STATUS_CRITICAL]),
                    legend=None,
                ),
                tooltip=["rating", "count"],
            )
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No feedback submitted yet.")

with col_d:
    st.subheader("Most-cited sources")
    doc_ids = conversations["source_doc_ids"].dropna().str.split(", ").explode()
    doc_ids = doc_ids[doc_ids != ""]
    if not doc_ids.empty:
        top_docs = doc_ids.value_counts().head(10).reset_index()
        top_docs.columns = ["doc_id", "count"]
        chart = (
            alt.Chart(top_docs)
            .mark_bar(color=BLUE)
            .encode(
                y=alt.Y("doc_id:N", title=None, sort="-x"),
                x=alt.X("count:Q", title="Times cited"),
                tooltip=["doc_id", "count"],
            )
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No source citations logged yet.")

st.divider()

col_e, col_f = st.columns(2)

with col_e:
    st.subheader("Questions by intent")
    st.caption(
        "Inferred from which analytical tool the agent actually called, not a separate "
        "classifier call - so it reflects real routing, not a guess at the question in isolation."
    )
    intents = conversations["intent"].dropna()
    if not intents.empty:
        intent_counts = intents.value_counts().reset_index()
        intent_counts.columns = ["intent", "count"]
        chart = (
            alt.Chart(intent_counts)
            .mark_bar(size=28)
            .encode(
                y=alt.Y("intent:N", title=None, sort="-x"),
                x=alt.X("count:Q", title="Questions"),
                color=alt.Color(
                    "intent:N", scale=alt.Scale(domain=sorted(intent_counts["intent"]), range=CATEGORICAL), legend=None
                ),
                tooltip=["intent", "count"],
            )
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No intent-labeled conversations yet (older rows logged before this field was added).")

with col_f:
    st.subheader("Tool success rate")
    st.caption("Among Ask ScanFlow questions that called at least one analytical tool.")
    tool_calls = conversations["tool_success"].dropna()
    if not tool_calls.empty:
        outcome_counts = tool_calls.map({True: "success", False: "error"}).value_counts().reset_index()
        outcome_counts.columns = ["outcome", "count"]
        chart = (
            alt.Chart(outcome_counts)
            .mark_bar(size=50)
            .encode(
                x=alt.X("outcome:N", title=None, sort=["success", "error"]),
                y=alt.Y("count:Q", title="Interactions"),
                color=alt.Color(
                    "outcome:N",
                    scale=alt.Scale(domain=["success", "error"], range=[STATUS_GOOD, STATUS_CRITICAL]),
                    legend=None,
                ),
                tooltip=["outcome", "count"],
            )
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No tool-calling conversations logged yet.")

st.subheader("Estimated LLM cost per day")
st.caption("Sum of per-interaction token cost (from the model's pricing table), by day.")
cost_rows = conversations.dropna(subset=["estimated_cost"])
if not cost_rows.empty:
    daily_cost = (
        cost_rows.assign(day=cost_rows["created_at"].dt.date)
        .groupby("day")["estimated_cost"]
        .sum()
        .reset_index()
    )
    chart = (
        alt.Chart(daily_cost)
        .mark_bar(color=BLUE)
        .encode(
            x=alt.X("day:T", title=None),
            y=alt.Y("estimated_cost:Q", title="Cost (USD)"),
            tooltip=["day:T", alt.Tooltip("estimated_cost:Q", format="$.4f")],
        )
    )
    st.altair_chart(chart, use_container_width=True)
else:
    st.caption("No cost-tracked conversations yet (older rows logged before this field was added).")

st.subheader("Data ingestion freshness")
st.caption("Source files downloaded and loaded by the Kestra ingestion pipeline (db/nhs_schema.py: source_files).")
try:
    source_files = get_source_files_df()
except Exception as e:
    source_files = pd.DataFrame()
    st.caption(f"(monitoring DB unavailable: {e})")

if not source_files.empty:
    source_files["downloaded_at"] = pd.to_datetime(source_files["downloaded_at"])
    chart = (
        alt.Chart(source_files)
        .mark_circle(size=120, color=BLUE)
        .encode(
            x=alt.X("downloaded_at:T", title="Downloaded"),
            y=alt.Y("dataset:N", title=None),
            size=alt.Size("row_count:Q", title="Rows loaded", legend=None),
            tooltip=["dataset", "reporting_period_id", "row_count", "downloaded_at:T"],
        )
    )
    st.altair_chart(chart, use_container_width=True)
    most_recent = source_files["downloaded_at"].max()
    st.caption(f"Most recent ingestion: {most_recent:%Y-%m-%d %H:%M UTC}")
else:
    st.caption("No source files recorded yet - run the ingestion pipeline first.")

st.divider()
with st.expander("Raw conversation log"):
    st.dataframe(conversations.sort_values("created_at", ascending=False), use_container_width=True)
