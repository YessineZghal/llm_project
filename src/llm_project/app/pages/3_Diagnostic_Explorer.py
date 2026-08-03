"""Diagnostic Explorer (plan.md Step 15): provider/test/date filters and
trend charts for waiting list, activity, and long-wait percentage. Three
separate single-hue charts rather than one dual-axis chart, since waiting
count, activity count, and a percentage are different units and scales -
combining them on one chart with two y-axes is the #1 chart-design mistake
this project's other pages already avoid (see Monitoring page conventions).
"""

import altair as alt
import pandas as pd
import streamlit as st

from llm_project.db.models import get_session
from llm_project.db.nhs_schema import DiagnosticTest, Provider, ProviderTestMonthMetric, ReportingPeriod

st.set_page_config(page_title="Diagnostic Explorer - ScanFlow AI", layout="wide")

BLUE = "#2a78d6"

st.title("Diagnostic Explorer")
st.caption(
    "Waiting-list, activity, and long-wait trends for one provider and diagnostic test, "
    "across every loaded reporting month."
)


@st.cache_data(ttl=300)
def load_reference():
    session = get_session()
    try:
        tests = [t.test_code for t in session.query(DiagnosticTest).order_by(DiagnosticTest.test_code)]
        providers = [(p.provider_code, p.provider_name) for p in session.query(Provider).order_by(Provider.provider_name)]
        return tests, providers
    finally:
        session.close()


@st.cache_data(ttl=300)
def load_history(provider_code: str, test_code: str) -> pd.DataFrame:
    session = get_session()
    try:
        periods = {p.period_id: p.period_month for p in session.query(ReportingPeriod).all()}
        rows = (
            session.query(ProviderTestMonthMetric)
            .filter_by(provider_code=provider_code, test_code=test_code)
            .all()
        )
        records = [
            {
                "period_id": r.period_id,
                "period_month": periods[r.period_id],
                "total_waiting": r.total_waiting,
                "total_activity": r.total_activity,
                "percentage_waiting_6_plus_weeks": r.percentage_waiting_6_plus_weeks,
            }
            for r in rows
        ]
        df = pd.DataFrame(records)
        return df.sort_values("period_month") if not df.empty else df
    finally:
        session.close()


tests, providers = load_reference()
if not tests or not providers:
    st.warning("No data loaded yet.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    provider_choice = st.selectbox("Provider", providers, format_func=lambda p: f"{p[1]} ({p[0]})")
with col2:
    test_choice = st.selectbox("Diagnostic test", tests)

df = load_history(provider_choice[0], test_choice)

if df.empty:
    st.info("No data for this provider and test.")
    st.stop()

if len(df) < 2:
    st.info("Only one reporting month is loaded for this provider and test - a trend needs at least two.")

st.subheader(f"{provider_choice[1]} - {test_choice}")

m1, m2, m3 = st.columns(3)
latest = df.iloc[-1]
m1.metric("Total waiting (latest)", f"{latest['total_waiting']:,.0f}")
m2.metric("Total activity (latest)", f"{latest['total_activity']:,.0f}")
m3.metric("Waiting 6+ weeks (latest)", f"{latest['percentage_waiting_6_plus_weeks']:.1f}%")

st.divider()

def line_chart(df: pd.DataFrame, y_col: str, y_title: str, y_format: str = ",.0f") -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_line(point=True, color=BLUE, strokeWidth=2)
        .encode(
            x=alt.X("period_month:T", title=None),
            y=alt.Y(f"{y_col}:Q", title=y_title, axis=alt.Axis(format=y_format)),
            tooltip=[alt.Tooltip("period_id:N", title="Period"), alt.Tooltip(f"{y_col}:Q", title=y_title, format=y_format)],
        )
        .properties(height=220)
    )

st.subheader("Waiting list")
st.altair_chart(line_chart(df, "total_waiting", "Total waiting"), use_container_width=True)

st.subheader("Activity")
st.altair_chart(line_chart(df, "total_activity", "Total activity"), use_container_width=True)

st.subheader("Percentage waiting six weeks or longer")
pct_chart = line_chart(df, "percentage_waiting_6_plus_weeks", "Waiting 6+ weeks (%)", y_format=".1f")
st.altair_chart(pct_chart, use_container_width=True)

st.divider()
with st.expander("Underlying data"):
    st.dataframe(
        df[["period_id", "total_waiting", "total_activity", "percentage_waiting_6_plus_weeks"]],
        use_container_width=True,
        hide_index=True,
    )
st.caption(
    "Source: src/llm_project/analytics/metrics.py -> provider_test_month_metrics "
    "(computed from NHS DM01 data; see DATA_SOURCES.md)."
)
