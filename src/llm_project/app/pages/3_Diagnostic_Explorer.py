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

from llm_project.analytics.tools import ALLOWED_TEST_CODES, NationalSummaryInput, ToolError, get_national_summary
from llm_project.db.models import get_session
from llm_project.db.nhs_schema import DiagnosticTest, Provider, ProviderTestMonthMetric, ReportingPeriod

st.set_page_config(page_title="Diagnostic Explorer - ScanFlow AI", layout="wide")

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE = "#2a78d6"

st.title("Diagnostic Explorer")
st.caption(
    "Waiting-list, activity, and long-wait trends for one provider and diagnostic test, "
    "across every loaded reporting month."
)


@st.cache_data(ttl=300)
def load_national_overview() -> pd.DataFrame:
    """One row per diagnostic test, from analytics.tools.get_national_summary -
    the same tool the agent calls for "national/overall" questions, so this
    panel and the chat answer are always backed by the identical computation."""
    rows = []
    for test_code in sorted(ALLOWED_TEST_CODES):
        try:
            summary = get_national_summary(NationalSummaryInput(test_code=test_code))
        except ToolError:
            continue
        rows.append(
            {
                "test_code": test_code,
                "period_id": summary.period_id,
                "provider_count": summary.provider_count,
                "total_waiting": summary.total_waiting,
                "total_activity": summary.total_activity,
                "national_pct": summary.national_percentage_waiting_6_plus_weeks,
                "average_pct": summary.average_percentage_waiting_6_plus_weeks,
            }
        )
    return pd.DataFrame(rows)


national_df = load_national_overview()
if not national_df.empty:
    st.subheader("National overview")
    st.caption(
        f"Every loaded provider, aggregated per diagnostic test, for {national_df['period_id'].iloc[0]} "
        "(src/llm_project/analytics/tools.py::get_national_summary - the same tool the agent uses)."
    )

    chart_df = pd.melt(
        national_df,
        id_vars=["test_code"],
        value_vars=["national_pct", "average_pct"],
        var_name="basis",
        value_name="percentage",
    )
    chart_df["basis"] = chart_df["basis"].map(
        {"national_pct": "National (waiting-weighted)", "average_pct": "Simple average across providers"}
    )
    chart = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=alt.X("test_code:N", title=None),
            xOffset="basis:N",
            y=alt.Y("percentage:Q", title="Waiting 6+ weeks (%)"),
            color=alt.Color(
                "basis:N",
                scale=alt.Scale(
                    domain=["National (waiting-weighted)", "Simple average across providers"],
                    range=[CATEGORICAL[0], CATEGORICAL[1]],
                ),
                title=None,
            ),
            tooltip=["test_code", "basis", alt.Tooltip("percentage:Q", format=".1f")],
        )
        .properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)
    st.caption(
        "The waiting-weighted national figure and the simple average across providers are shown "
        "separately on purpose - averaging percentages across providers of very different sizes "
        "would misrepresent the true national rate, so the two are never collapsed into one number."
    )

    with st.expander("National totals by test"):
        st.dataframe(
            national_df.rename(
                columns={
                    "test_code": "Test", "period_id": "Period", "provider_count": "Providers",
                    "total_waiting": "Total waiting", "total_activity": "Total activity",
                    "national_pct": "National % (weighted)", "average_pct": "Average % (unweighted)",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("Provider drill-down")


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
