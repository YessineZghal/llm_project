"""Capacity Scenario (plan.md Step 15): current activity, additional monthly
activity, assumed demand (implied from recent data), duration, and a clear
simplified-model warning - answers plan.md's sample question 10 ("What would
a simplified increase of 200 MRI procedures per month do to the waiting-list
balance, assuming demand stays constant?").
"""

import altair as alt
import pandas as pd
import streamlit as st

from llm_project.analytics.tools import CapacityScenarioInput, ToolError, simulate_capacity_change
from llm_project.db.models import get_session
from llm_project.db.nhs_schema import DiagnosticTest, Provider, ReportingPeriod

st.set_page_config(page_title="Capacity Scenario - ScanFlow AI", layout="wide")

BLUE = "#2a78d6"

st.title("Capacity Scenario")
st.warning(
    "This is a simplified linear projection for illustration only, not a forecast. It assumes monthly "
    "demand stays constant at the level implied by recent data and does not account for seasonality, "
    "referral changes, staffing, or any other real-world factor."
)


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

col1, col2, col3 = st.columns(3)
with col1:
    provider_choice = st.selectbox("Provider", providers, format_func=lambda p: f"{p[1]} ({p[0]})")
with col2:
    test_choice = st.selectbox("Diagnostic test", tests)
with col3:
    period_choice = st.selectbox("Baseline reporting period", periods)

col4, col5 = st.columns(2)
with col4:
    additional_activity = st.slider("Additional monthly activity", -200, 500, 200, step=10)
with col5:
    duration_months = st.slider("Months to project forward", 1, 24, 6)

if st.button("Run scenario", type="primary"):
    try:
        result = simulate_capacity_change(
            CapacityScenarioInput(
                provider_code=provider_choice[0], test_code=test_choice,
                additional_monthly_activity=additional_activity, duration_months=duration_months,
                period_id=period_choice,
            )
        )
        st.session_state["scenario_result"] = result
    except ToolError as e:
        st.session_state["scenario_result"] = None
        st.error(str(e))

result = st.session_state.get("scenario_result")
if result is not None:
    for w in result.warnings:
        st.info(w)

    m1, m2, m3 = st.columns(3)
    m1.metric("Baseline waiting list", f"{result.baseline_waiting_list:,}")
    m2.metric("Baseline monthly activity", f"{result.baseline_monthly_activity:,}")
    m3.metric("Implied monthly demand", f"{result.implied_monthly_demand:,}")

    df = pd.DataFrame(
        [{"month": 0, "projected_waiting_list": result.baseline_waiting_list}]
        + [{"month": p.month, "projected_waiting_list": p.projected_waiting_list} for p in result.projection]
    )

    st.subheader("Projected waiting list")
    chart = (
        alt.Chart(df)
        .mark_line(point=True, color=BLUE, strokeWidth=2)
        .encode(
            x=alt.X("month:Q", title="Months from baseline", axis=alt.Axis(tickMinStep=1)),
            y=alt.Y("projected_waiting_list:Q", title="Projected waiting list"),
            tooltip=["month", alt.Tooltip("projected_waiting_list:Q", format=",.0f")],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, use_container_width=True)

    trend_note = (
        "grows" if df["projected_waiting_list"].iloc[-1] > result.baseline_waiting_list
        else "shrinks" if df["projected_waiting_list"].iloc[-1] < result.baseline_waiting_list
        else "stays flat"
    )
    st.write(
        f"Under this scenario, {result.provider_name}'s projected {result.test_code} waiting list "
        f"**{trend_note}** over {duration_months} months, from {result.baseline_waiting_list:,} "
        f"to {df['projected_waiting_list'].iloc[-1]:,.0f}, assuming monthly demand stays at the "
        f"implied {result.implied_monthly_demand:,} and monthly activity becomes "
        f"{result.baseline_monthly_activity + result.additional_monthly_activity:,} "
        f"({result.baseline_monthly_activity:,} baseline + {result.additional_monthly_activity:,})."
    )

    st.divider()
    with st.expander("Underlying data"):
        st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(result.source)
else:
    st.info("Choose a provider, test, and scenario parameters, then click Run scenario.")
