"""ScanFlow AI Streamlit interface. "Ask ScanFlow" uses the agent
(src/llm_project/rag/agent.py, plan.md Steps 11-13: tool-calling routed
between analytical tools and RAG retrieval); "Rank providers" and "Provider
profile" call the analytical tools directly with no LLM in the loop, for
users who want a structured lookup rather than a conversation. Either way,
every number displayed comes from a tool, never from the model's own
arithmetic.
"""

import time

import streamlit as st

from llm_project.analytics.tools import (
    ALLOWED_RANK_METRICS,
    ProviderProfileInput,
    RankProvidersInput,
    ToolError,
    get_provider_profile,
    rank_provider_waits,
)
from llm_project.config import OPENAI_CHAT_MODEL
from llm_project.db.client import log_conversation, log_feedback
from llm_project.db.models import get_session
from llm_project.db.nhs_schema import DiagnosticTest, Provider, ReportingPeriod
from llm_project.rag.agent import ask_agent

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


def extract_source_doc_ids(messages: list) -> list[str]:
    """Pull document ids out of search_knowledge_base / retrieve_metric_definition
    tool results in the agent's message trace, for monitoring's "most-cited
    source documents" chart. Content-based detection (a list of docs with an
    "id" key, or a single result with a "document_id" key) rather than
    correlating tool_call_id, since either shape is unambiguous on its own."""
    import json as _json

    ids: list[str] = []
    for m in messages:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        if role != "tool":
            continue
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        try:
            parsed = _json.loads(content)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, list):
            ids.extend(d["id"] for d in parsed if isinstance(d, dict) and "id" in d)
        elif isinstance(parsed, dict) and parsed.get("document_id"):
            ids.append(parsed["document_id"])
    return ids


def render_feedback(state_key: str):
    """Thumbs up/down wired to log_feedback, persisted in session_state so it
    survives the rerun triggered by the buttons themselves (plan.md Step 16)."""
    conv_id = st.session_state.get(f"{state_key}_conv_id")
    if not conv_id:
        return
    voted = st.session_state.get(f"{state_key}_voted")
    col1, col2, _ = st.columns([1, 1, 10])
    with col1:
        if st.button("Helpful", key=f"{state_key}_up", disabled=voted is not None):
            log_feedback(conv_id, 1)
            st.session_state[f"{state_key}_voted"] = "up"
            st.rerun()
    with col2:
        if st.button("Not helpful", key=f"{state_key}_down", disabled=voted is not None):
            log_feedback(conv_id, -1)
            st.session_state[f"{state_key}_voted"] = "down"
            st.rerun()
    if voted:
        st.caption(f"Thanks for the feedback ({voted}).")


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

tab_ask, tab_rank, tab_profile = st.tabs(["Ask ScanFlow", "Rank providers", "Provider profile"])

with tab_ask:
    st.subheader("Ask a question in your own words")
    st.caption(
        "Routed to analytical tools or the knowledge base as needed. Individual clinical "
        "questions (for example, predicting your own wait time) will be declined."
    )

    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages = []  # each: {role, content, conv_id, voted}
    if "agent_history" not in st.session_state:
        st.session_state.agent_history = []

    for i, message in enumerate(st.session_state.agent_messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant" and message.get("conv_id"):
                voted = message.get("voted")
                col1, col2, _ = st.columns([1, 1, 10])
                with col1:
                    if st.button("Helpful", key=f"ask_up_{i}", disabled=voted is not None):
                        log_feedback(message["conv_id"], 1)
                        message["voted"] = "up"
                        st.rerun()
                with col2:
                    if st.button("Not helpful", key=f"ask_down_{i}", disabled=voted is not None):
                        log_feedback(message["conv_id"], -1)
                        message["voted"] = "down"
                        st.rerun()
                if voted:
                    st.caption(f"Thanks for the feedback ({voted}).")

    question = st.chat_input("Ask about NHS diagnostic waiting times...")
    if question:
        st.session_state.agent_messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                start = time.time()
                loop_result = ask_agent(question, previous_messages=st.session_state.agent_history or None)
                elapsed = time.time() - start
                answer = loop_result.last_message
                st.session_state.agent_history = loop_result.all_messages
                st.markdown(answer)

            conv_id = None
            try:
                conv_id = log_conversation(
                    question=question, answer=answer, mode="agent", model=OPENAI_CHAT_MODEL,
                    response_time_seconds=elapsed, retrieval_method=None, prompt_variant=None,
                    source_doc_ids=extract_source_doc_ids(loop_result.new_messages),
                )
            except Exception as e:
                st.caption(f"(monitoring DB unavailable: {e})")

        st.session_state.agent_messages.append(
            {"role": "assistant", "content": answer, "conv_id": conv_id, "voted": None}
        )
        st.rerun()

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
            question = (
                f"Top {rank_limit} providers by {rank_metric} for {rank_test} "
                f"in {result.period_id} ({rank_order})"
            )
            answer = ", ".join(f"{r.provider_name} ({r.value})" for r in result.results) or "no results"
            conv_id = None
            try:
                conv_id = log_conversation(
                    question=question, answer=answer, mode="rank_provider_waits", model="tool:rank_provider_waits",
                    response_time_seconds=result.execution_time_ms / 1000, retrieval_method=None, prompt_variant=None,
                    source_doc_ids=[],
                )
            except Exception as e:
                st.session_state["rank_db_error"] = str(e)

            st.session_state["rank_result"] = result
            st.session_state["rank_conv_id"] = conv_id
            st.session_state["rank_voted"] = None
        except ToolError as e:
            st.session_state["rank_result"] = None
            st.error(str(e))

    result = st.session_state.get("rank_result")
    if result is not None:
        st.success(f"Reporting period: **{result.period_id}** - source: {result.source}")
        st.dataframe(
            [{"Provider": r.provider_name, "Code": r.provider_code, result.metric: r.value} for r in result.results],
            use_container_width=True,
            hide_index=True,
        )
        for w in result.warnings:
            st.info(w)
        if st.session_state.get("rank_db_error"):
            st.caption(f"(monitoring DB unavailable: {st.session_state['rank_db_error']})")
        render_feedback("rank")

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
            conv_id = None
            try:
                conv_id = log_conversation(
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
                st.session_state["profile_db_error"] = str(e)

            st.session_state["profile_result"] = profile
            st.session_state["profile_conv_id"] = conv_id
            st.session_state["profile_voted"] = None
        except ToolError as e:
            st.session_state["profile_result"] = None
            st.error(str(e))

    profile = st.session_state.get("profile_result")
    if profile is not None:
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

        no_history = "n/a (no prior month loaded)"
        waiting_mom = (
            f"{profile.waiting_list_monthly_change_pct:+.1f}%"
            if profile.waiting_list_monthly_change_pct is not None
            else no_history
        )
        activity_mom = (
            f"{profile.activity_monthly_change_pct:+.1f}%"
            if profile.activity_monthly_change_pct is not None
            else no_history
        )

        col_a, col_b = st.columns(2)
        col_a.write(f"**Waiting-list change (MoM):** {waiting_mom}")
        col_b.write(f"**Activity change (MoM):** {activity_mom}")
        st.write(f"**Persistent pressure:** {profile.persistent_pressure_months} of the loaded prior months")

        for w in profile.warnings:
            st.info(w)
        if st.session_state.get("profile_db_error"):
            st.caption(f"(monitoring DB unavailable: {st.session_state['profile_db_error']})")
        render_feedback("profile")

st.divider()
st.caption(
    "Data: NHS England Monthly Diagnostic Waiting Times and Activity, under the Open Government Licence v3.0. "
    "See DATA_SOURCES.md. This is an independent educational project, not endorsed by NHS England."
)
