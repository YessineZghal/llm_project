"""Provider Comparison (plan.md Step 15): 2-5 providers, same test and
period, absolute and normalized values. Two separate charts (waiting count,
percentage) rather than one dual-axis chart - different units and scales.
"""

import altair as alt
import pandas as pd
import streamlit as st

from llm_project.analytics.tools import CompareProvidersInput, ToolError, compare_provider_waits
from llm_project.db.models import get_session
from llm_project.db.nhs_schema import DiagnosticTest, Provider, ReportingPeriod

st.set_page_config(page_title="Provider Comparison - ScanFlow AI", layout="wide")

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

st.title("Provider Comparison")
st.caption("Compare 2 to 5 providers on the same diagnostic test and reporting period.")


@st.cache_data(ttl=300)
def load_reference():
    session = get_session()
    try:
        tests = [t.test_code for t in session.query(DiagnosticTest).order_by(DiagnosticTest.test_code)]
        periods = [p.period_id for p in session.query(ReportingPeriod).order_by(ReportingPeriod.period_month.desc())]
        providers = [(p.provider_code, p.provider_name) for p in session.query(Provider).order_by(Provider.provider_name)]
        return tests, periods, providers
    finally:
        session.close()


tests, periods, providers = load_reference()
if not tests or not periods:
    st.warning("No data loaded yet.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    test_choice = st.selectbox("Diagnostic test", tests)
with col2:
    period_choice = st.selectbox("Reporting period", periods)

selected = st.multiselect(
    "Providers (2 to 5)", providers, format_func=lambda p: f"{p[1]} ({p[0]})", max_selections=5,
)

if len(selected) < 2:
    st.info("Select at least 2 providers to compare.")
    st.stop()

try:
    result = compare_provider_waits(
        CompareProvidersInput(
            provider_codes=[p[0] for p in selected], test_code=test_choice, period_id=period_choice
        )
    )
except ToolError as e:
    st.error(str(e))
    st.stop()

for w in result.warnings:
    st.info(w)

df = pd.DataFrame(
    [
        {
            "Provider": e.provider_name,
            "total_waiting": e.total_waiting,
            "percentage_waiting_6_plus_weeks": e.percentage_waiting_6_plus_weeks,
            "total_activity": e.total_activity,
            "pressure_proxy": e.pressure_proxy,
        }
        for e in result.entries
    ]
)
provider_domain = df["Provider"].tolist()

st.success(f"Reporting period: **{result.period_id}** - test: **{result.test_code}**")

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Total waiting")
    chart = (
        alt.Chart(df)
        .mark_bar(size=40)
        .encode(
            x=alt.X("Provider:N", title=None, sort=None, axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("total_waiting:Q", title="Total waiting"),
            color=alt.Color("Provider:N", scale=alt.Scale(domain=provider_domain, range=CATEGORICAL), legend=None),
            tooltip=["Provider", "total_waiting"],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, use_container_width=True)

with col_b:
    st.subheader("Percentage waiting six weeks or longer")
    chart = (
        alt.Chart(df)
        .mark_bar(size=40)
        .encode(
            x=alt.X("Provider:N", title=None, sort=None, axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("percentage_waiting_6_plus_weeks:Q", title="Waiting 6+ weeks (%)"),
            color=alt.Color("Provider:N", scale=alt.Scale(domain=provider_domain, range=CATEGORICAL), legend=None),
            tooltip=["Provider", alt.Tooltip("percentage_waiting_6_plus_weeks:Q", format=".1f")],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, use_container_width=True)

st.subheader("Total activity")
chart = (
    alt.Chart(df)
    .mark_bar(size=40)
    .encode(
        x=alt.X("Provider:N", title=None, sort=None, axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("total_activity:Q", title="Total activity"),
        color=alt.Color("Provider:N", scale=alt.Scale(domain=provider_domain, range=CATEGORICAL), legend=None),
        tooltip=["Provider", "total_activity"],
    )
    .properties(height=280)
)
st.altair_chart(chart, use_container_width=True)

st.divider()
with st.expander("Underlying data"):
    st.dataframe(df, use_container_width=True, hide_index=True)
st.caption(result.source)
