"""Bottleneck Ranking (plan.md Step 15): test, month, weighting scenario,
and data-quality filter, with score components shown alongside the ranking
so the score is explainable rather than a single opaque number. The
bottleneck score is a project-specific indicator, not an official NHS
metric - stated prominently, per plan.md's own failure control for this page.
"""

import altair as alt
import pandas as pd
import streamlit as st

from llm_project.analytics.tools import BottleneckRankingInput, ToolError, get_bottleneck_ranking
from llm_project.db.models import get_session
from llm_project.db.nhs_schema import DiagnosticTest, ReportingPeriod

st.set_page_config(page_title="Bottleneck Ranking - ScanFlow AI", layout="wide")

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

st.title("Bottleneck Ranking")
st.warning(
    "The bottleneck score is a project-specific indicator for relative comparison within the same "
    "diagnostic test and reporting month. It is not an official NHS metric and is not clinically validated."
)


@st.cache_data(ttl=300)
def load_reference():
    session = get_session()
    try:
        tests = [t.test_code for t in session.query(DiagnosticTest).order_by(DiagnosticTest.test_code)]
        periods = [p.period_id for p in session.query(ReportingPeriod).order_by(ReportingPeriod.period_month.desc())]
        return tests, periods
    finally:
        session.close()


tests, periods = load_reference()
if not tests or not periods:
    st.warning("No data loaded yet.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
with col1:
    test_choice = st.selectbox("Diagnostic test", tests)
with col2:
    period_choice = st.selectbox("Reporting period", periods)
with col3:
    scenario_choice = st.selectbox(
        "Weighting scenario", ["balanced", "waiting_focused", "capacity_focused"],
        help="Same components, different weights - shows how sensitive the ranking is to the weighting assumption.",
    )
with col4:
    quality_choice = st.selectbox(
        "Data quality", ["any", "complete_only"],
        format_func=lambda v: "Any" if v == "any" else "Complete history only",
    )
limit = st.slider("Number of providers", 3, 25, 10)

try:
    result = get_bottleneck_ranking(
        BottleneckRankingInput(
            test_code=test_choice, period_id=period_choice, weighting_scenario=scenario_choice,
            limit=limit, min_quality=quality_choice,
        )
    )
except ToolError as e:
    st.error(str(e))
    st.stop()

for w in result.warnings:
    st.info(w)

if not result.results:
    st.stop()

df = pd.DataFrame(
    [
        {
            "Provider": e.provider_name,
            "score": e.score,
            "long_wait": e.component_long_wait,
            "waiting_growth": e.component_waiting_growth,
            "activity_imbalance": e.component_activity_imbalance,
            "persistence": e.component_persistence,
            "cdc_indicator": e.component_cdc_indicator,
            "quality_flag": e.quality_flag,
        }
        for e in result.results
    ]
)
provider_order = df["Provider"].tolist()

st.success(f"Reporting period: **{result.period_id}** - test: **{result.test_code}** - scenario: **{scenario_choice}**")

st.subheader("Ranked bottleneck score")
chart = (
    alt.Chart(df)
    .mark_bar(color=CATEGORICAL[0])
    .encode(
        y=alt.Y("Provider:N", title=None, sort="-x"),
        x=alt.X("score:Q", title="Bottleneck score (0-100)"),
        tooltip=["Provider", alt.Tooltip("score:Q", format=".1f"), "quality_flag"],
    )
    .properties(height=max(220, 28 * len(df)))
)
st.altair_chart(chart, use_container_width=True)

st.subheader("Score components")
st.caption("Each component is normalized 0-100 within this test/period's providers, before the scenario's weights are applied.")
components = ["long_wait", "waiting_growth", "activity_imbalance", "persistence", "cdc_indicator"]
component_labels = {
    "long_wait": "Long-wait %", "waiting_growth": "Waiting-list growth",
    "activity_imbalance": "Activity imbalance", "persistence": "Persistence", "cdc_indicator": "CDC indicator",
}
long_df = df.melt(id_vars=["Provider"], value_vars=components, var_name="component", value_name="value")
long_df = long_df.dropna(subset=["value"])
long_df["component"] = long_df["component"].map(component_labels)

if not long_df.empty:
    chart = (
        alt.Chart(long_df)
        .mark_bar()
        .encode(
            x=alt.X("Provider:N", title=None, sort=provider_order, axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("value:Q", title="Component value (0-100)"),
            xOffset="component:N",
            color=alt.Color(
                "component:N",
                scale=alt.Scale(domain=list(component_labels.values()), range=CATEGORICAL),
                legend=alt.Legend(title=None, orient="bottom"),
            ),
            tooltip=["Provider", "component", alt.Tooltip("value:Q", format=".1f")],
        )
        .properties(height=340)
    )
    st.altair_chart(chart, use_container_width=True)
else:
    st.caption("No component data available to break down for this selection.")

st.divider()
with st.expander("Underlying data"):
    st.dataframe(df, use_container_width=True, hide_index=True)
st.caption(result.source)
