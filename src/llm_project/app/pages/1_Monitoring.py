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

from llm_project.db.client import get_conversations_df, get_feedback_df
from llm_project.search.retriever import METHODS

st.set_page_config(page_title="Monitoring — LLM/RAG/Agents Research Assistant", page_icon="📊", layout="wide")

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE = "#2a78d6"
STATUS_GOOD = "#0ca30c"
STATUS_CRITICAL = "#d03b3b"

st.title("📊 Monitoring")
st.caption("Usage and feedback for the LLM/RAG/Agents Research Assistant, logged to Postgres on every chat turn.")

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

col1, col2, col3, col4 = st.columns(4)
col1.metric("Conversations", n_conversations)
col2.metric("Feedback votes", n_feedback)
col3.metric("👍 rate", f"{up_rate:.0%}" if up_rate is not None else "—")
col4.metric("Avg response time", f"{avg_response_time:.1f}s")

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
    st.subheader("RAG vs Agent mode")
    mode_counts = conversations["mode"].value_counts().reset_index()
    mode_counts.columns = ["mode", "count"]
    chart = (
        alt.Chart(mode_counts)
        .mark_bar(size=50)
        .encode(
            x=alt.X("mode:N", title=None, sort="-y"),
            y=alt.Y("count:Q", title="Conversations"),
            color=alt.Color("mode:N", scale=alt.Scale(domain=["rag", "agent"], range=CATEGORICAL), legend=None),
            tooltip=["mode", "count"],
        )
    )
    st.altair_chart(chart, use_container_width=True)

with col_b:
    st.subheader("Retrieval method usage (RAG mode)")
    rag_rows = conversations[conversations["mode"] == "rag"]
    if rag_rows["retrieval_method"].notna().any():
        method_counts = rag_rows["retrieval_method"].value_counts().reset_index()
        method_counts.columns = ["method", "count"]
        chart = (
            alt.Chart(method_counts)
            .mark_bar(size=35)
            .encode(
                x=alt.X("method:N", title=None, sort="-y"),
                y=alt.Y("count:Q", title="Conversations"),
                color=alt.Color("method:N", scale=alt.Scale(domain=METHODS, range=CATEGORICAL), legend=None),
                tooltip=["method", "count"],
            )
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No RAG-mode conversations yet.")

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
        fb_counts = feedback["rating"].map({1: "👍 up", -1: "👎 down"}).value_counts().reset_index()
        fb_counts.columns = ["rating", "count"]
        chart = (
            alt.Chart(fb_counts)
            .mark_bar(size=50)
            .encode(
                x=alt.X("rating:N", title=None, sort=["👍 up", "👎 down"]),
                y=alt.Y("count:Q", title="Votes"),
                color=alt.Color(
                    "rating:N",
                    scale=alt.Scale(domain=["👍 up", "👎 down"], range=[STATUS_GOOD, STATUS_CRITICAL]),
                    legend=None,
                ),
                tooltip=["rating", "count"],
            )
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No feedback submitted yet.")

with col_d:
    st.subheader("Most-cited source papers")
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
with st.expander("Raw conversation log"):
    st.dataframe(conversations.sort_values("created_at", ascending=False), use_container_width=True)
