"""ScanFlow AI — minimal Streamlit slice (plan.md Milestone 3: "one question
produces a validated result and source period"). Calls the analytical tools
directly; no LLM/RAG yet (that lands in Milestones 4-6) — every number here
comes straight from src/llm_project/analytics/, never from a model.
"""

import streamlit as st

from llm_project.analytics.tools import (
    ALLOWED_RANK_METRICS,
    ProviderProfileInput,
    RankProvidersInput,
    ToolError,
    get_provider_profile,
    rank_provider_waits,
)
from llm_project.db.client import log_conversation
from llm_project.db.models import get_session
from llm_project.db.nhs_schema import DiagnosticTest, Provider, ReportingPeriod

st.set_page_config(page_title="ScanFlow AI", layout="wide")


@st.cache_data(ttl=300)
def load_reference_data():
    session = get_session()
    try:
        tests = [t.test_code for t in session.query(DiagnosticTest).order_by(DiagnosticTest.test_code)]
        periods = [
            p.period_id for p in session.query(ReportingPeriod).order_by(ReportingPeriod.period_month.desc())
        ]
        providers = [
            (p.provider_code, p.provider_name)
            for p in session.query(Provider).order_by(Provider.provider_name)
        ]
        return tests, periods, providers
    finally:
        session.close()


st.title("ScanFlow AI")
st.caption(
    "Diagnostic waiting-time and capacity insight from NHS England's published data "
    "(Monthly Diagnostic Waiting Times and Activity). Not an official NHS product; "
    "aggregate operational data only, not clinical or patient-level information."
)

tests, periods, providers = load_reference_data()

if not tests or not periods:
    st.warning("No data loaded yet. Run `uv run python -m llm_project.ingest.nhs_pipeline ...` first.")
    st.stop()

tab_rank, tab_profile = st.tabs(["Rank providers", "Provider profile"])

with tab_rank:
    st.subheader("Which providers have the highest [metric] for a diagnostic test?")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        rank_test = st.selectbox("Diagnostic test", tests, key="rank_test")
    with col2:
        rank_period = st.selectbox("Reporting period", periods, key="rank_period")
    with col3:
        rank_metric = st.selectbox("Metric", sorted(ALLOWED_RANK_METRICS), key="rank_metric")
    with col4:
        rank_order = st.selectbox("Order", ["descending", "ascending"], key="rank_order")
    rank_limit = st.slider("Number of providers", 1, 25, 5, key="rank_limit")

    if st.button("Rank providers", type="primary"):
        try:
            result = rank_provider_waits(
                RankProvidersInput(
                    test_code=rank_test,
                    period_id=rank_period,
                    metric=rank_metric,
                    sort_order=rank_order,
                    limit=rank_limit,
                )
            )
            st.success(f"Reporting period: **{result.period_id}** - source: {result.source}")
            st.dataframe(
                [{"Provider": r.provider_name, "Code": r.provider_code, rank_metric: r.value} for r in result.results],
                use_container_width=True,
                hide_index=True,
            )
            for w in result.warnings:
                st.info(w)

            question = f"Top {rank_limit} providers by {rank_metric} for {rank_test} in {result.period_id} ({rank_order})"
            answer = ", ".join(f"{r.provider_name} ({r.value})" for r in result.results) or "no results"
            try:
                log_conversation(
                    question=question, answer=answer, mode="rank_provider_waits", model="tool:rank_provider_waits",
                    response_time_seconds=result.execution_time_ms / 1000, retrieval_method=None, prompt_variant=None,
                    source_doc_ids=[],
                )
            except Exception as e:
                st.caption(f"(monitoring DB unavailable: {e})")
        except ToolError as e:
            st.error(str(e))

with tab_profile:
    st.subheader("Provider waiting-time and activity profile")
    col1, col2, col3 = st.columns(3)
    with col1:
        provider_choice = st.selectbox(
            "Provider", providers, format_func=lambda p: f"{p[1]} ({p[0]})", key="profile_provider"
        )
    with col2:
        profile_test = st.selectbox("Diagnostic test", tests, key="profile_test")
    with col3:
        profile_period = st.selectbox("Reporting period", periods, key="profile_period")

    if st.button("Get profile", type="primary"):
        try:
            profile = get_provider_profile(
                ProviderProfileInput(provider_code=provider_choice[0], test_code=profile_test, period_id=profile_period)
            )
            st.success(f"Reporting period: **{profile.period_id}** - source: {profile.source}")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total waiting", f"{profile.total_waiting:,}")
            m2.metric("Waiting 6+ weeks", f"{profile.waiting_6_plus_weeks:,}", f"{profile.percentage_waiting_6_plus_weeks:.1f}%")
            m3.metric("Total activity", f"{profile.total_activity:,}")
            m4.metric(
                "Pressure proxy",
                f"{profile.pressure_proxy:.1f}pp" if profile.pressure_proxy is not None else "n/a",
                help="Waiting-list growth minus activity growth, month-over-month. Positive = waiting growing faster than activity.",
            )

            col_a, col_b = st.columns(2)
            col_a.write(
                f"**Waiting-list change (MoM):** "
                f"{f'{profile.waiting_list_monthly_change_pct:+.1f}%' if profile.waiting_list_monthly_change_pct is not None else 'n/a (no prior month loaded)'}"
            )
            col_b.write(
                f"**Activity change (MoM):** "
                f"{f'{profile.activity_monthly_change_pct:+.1f}%' if profile.activity_monthly_change_pct is not None else 'n/a (no prior month loaded)'}"
            )
            st.write(f"**Persistent pressure:** {profile.persistent_pressure_months} of the loaded prior months")

            for w in profile.warnings:
                st.info(w)

            try:
                log_conversation(
                    question=f"Profile for {profile.provider_name} / {profile.test_code} / {profile.period_id}",
                    answer=(
                        f"{profile.total_waiting} waiting ({profile.percentage_waiting_6_plus_weeks:.1f}% "
                        f"6+ weeks), {profile.total_activity} activity"
                    ),
                    mode="get_provider_profile", model="tool:get_provider_profile",
                    response_time_seconds=profile.execution_time_ms / 1000, retrieval_method=None, prompt_variant=None,
                    source_doc_ids=[],
                )
            except Exception as e:
                st.caption(f"(monitoring DB unavailable: {e})")
        except ToolError as e:
            st.error(str(e))

st.divider()
st.caption(
    "Data: NHS England Monthly Diagnostic Waiting Times and Activity, under the Open Government Licence v3.0. "
    "See DATA_SOURCES.md. This is an independent educational project, not endorsed by NHS England."
)
