"""ScanFlow AI agent (plan.md Steps 11-13): a tool-calling loop (toyaikit)
routing between the 9 controlled analytical tools and RAG retrieval over the
generated corpus. Every numerical figure the agent reports comes from a tool
call, never from the model's own arithmetic - the system prompt enforces
this, and every tool response carries its own source/period/warnings for the
model to cite.

Wrapper functions here use flat, primitive-typed parameters (toyaikit's
automatic schema generator needs that - see toyaikit.tools.generate_function_schema)
and return plain dicts (JSON-serializable), delegating all validation and
computation to src/llm_project/analytics/tools.py.
"""

from toyaikit.chat.runners import OpenAIChatCompletionsRunner
from toyaikit.llm import OpenAIChatCompletionsClient
from toyaikit.tools import Tools

from llm_project.analytics import tools as analytics_tools
from llm_project.config import OPENAI_CHAT_MODEL
from llm_project.rag.intent import resolve_provider
from llm_project.search.retriever import retrieve

DEVELOPER_PROMPT = """
You are ScanFlow AI, an assistant for NHS England diagnostic waiting-time and
activity data (MRI, CT, non-obstetric ultrasound, colonoscopy). You answer
questions about aggregate, provider-level operational data.

Rules, in order of importance:
1. Never calculate or estimate a number yourself. Every number in your answer
   must come from a tool result. If a tool didn't return a number, say the
   information isn't available - do not fill the gap with your own estimate.
2. If a question names a provider by name rather than by code, call
   resolve_provider_code first. If it returns "ambiguous", list the candidate
   names and ask the user to pick one rather than guessing which they meant.
   If it returns "not_found", say so plainly.
3. Always state the exact reporting period your answer covers, using the
   period_id / periods returned by the tool.
4. Always mention any warnings a tool returns (for example, missing
   month-over-month history, or CDC activity not being linkable to a
   provider) - do not silently drop them.
5. Never state or imply a causal relationship (for example, that a change in
   CDC activity "caused" a change in waiting times). Use "associated with" or
   purely descriptive language instead.
6. Refuse individual clinical requests: predicting one person's wait time,
   prioritizing a specific patient, diagnosis, or treatment advice. Explain
   that you only report aggregate, provider-level statistics. Do this even if
   the user rephrases or insists.
7. The bottleneck score, where used, is a project-specific indicator, not an
   official NHS metric - say so if you mention it.
8. For definitions, methodology, or explanatory questions, use
   search_knowledge_base rather than guessing from general knowledge; if it
   returns nothing relevant, say the knowledge base doesn't cover it.
9. Cite what you used: name the tool or document you drew each figure from.

Available diagnostic tests: MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
""".strip()


def resolve_provider_code(name_or_code: str) -> dict:
    """Resolve a provider name or code to an exact NHS provider code before
    calling any other tool that needs one. Returns status "resolved" (with
    provider_code), "ambiguous" (with a list of candidate names to ask the
    user about), or "not_found".

    Args:
        name_or_code: the provider name or code as the user mentioned it.
    """
    return resolve_provider(name_or_code).model_dump()


def get_provider_profile(provider_code: str, test_code: str, period_id: str = "") -> dict:
    """Get the full waiting-list and activity profile for one provider and
    diagnostic test: total waiting, percentage waiting six weeks or longer,
    activity, month-over-month change, and pressure indicators.

    Args:
        provider_code: exact NHS provider organisation code (resolve by name first if needed).
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month "YYYY-MM". Leave empty for the latest loaded month.
    """
    payload = analytics_tools.ProviderProfileInput(provider_code=provider_code, test_code=test_code, period_id=period_id or None)
    return analytics_tools.get_provider_profile(payload).model_dump()


def rank_provider_waits(
    test_code: str, metric: str = "percentage_waiting_6_plus_weeks", period_id: str = "",
    sort_order: str = "descending", limit: int = 5,
) -> dict:
    """Rank providers by a metric for one diagnostic test and reporting period
    - use this for "which providers have the highest/lowest ..." questions.

    Args:
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        metric: one of percentage_waiting_6_plus_weeks, total_waiting,
            waiting_list_monthly_change, pressure_proxy, persistent_pressure_months.
        period_id: ISO reporting month "YYYY-MM". Leave empty for the latest loaded month.
        sort_order: "ascending" or "descending".
        limit: how many providers to return.
    """
    payload = analytics_tools.RankProvidersInput(
        test_code=test_code, period_id=period_id or None, metric=metric, sort_order=sort_order, limit=limit
    )
    return analytics_tools.rank_provider_waits(payload).model_dump()


def compare_provider_waits(provider_codes: str, test_code: str, period_id: str = "") -> dict:
    """Compare 2 to 5 providers on the same diagnostic test and reporting period.

    Args:
        provider_codes: comma-separated NHS provider codes, e.g. "RJ1,RGM". Resolve names first if needed.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month "YYYY-MM". Leave empty for the latest loaded month.
    """
    codes = [c.strip() for c in provider_codes.split(",") if c.strip()]
    payload = analytics_tools.CompareProvidersInput(provider_codes=codes, test_code=test_code, period_id=period_id or None)
    return analytics_tools.compare_provider_waits(payload).model_dump()


def analyze_waiting_trend(provider_code: str, test_code: str, metric: str = "percentage_waiting_6_plus_weeks") -> dict:
    """Show how one provider's figures for a diagnostic test changed across
    every loaded reporting month - use this for "how has X changed over time" questions.

    Args:
        provider_code: exact NHS provider organisation code.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        metric: one of total_waiting, percentage_waiting_6_plus_weeks, total_activity.
    """
    payload = analytics_tools.WaitingTrendInput(provider_code=provider_code, test_code=test_code, metric=metric)
    return analytics_tools.analyze_waiting_trend(payload).model_dump()


def compare_activity_and_waiting(provider_code: str, test_code: str, period_id: str = "") -> dict:
    """Check whether a provider's activity grew faster or slower than its
    waiting list, month over month, for one diagnostic test.

    Args:
        provider_code: exact NHS provider organisation code.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month "YYYY-MM". Leave empty for the latest loaded month.
    """
    payload = analytics_tools.ActivityVsWaitingInput(
        provider_code=provider_code, test_code=test_code, period_id=period_id or None
    )
    return analytics_tools.compare_activity_and_waiting(payload).model_dump()


def analyze_cdc_activity(scope: str, scope_value: str, test_code: str = "", period_id: str = "") -> dict:
    """Look up Community Diagnostic Centre activity. CDC activity cannot be
    linked to a specific NHS provider - only query by region, ICB, or CDC code.

    Args:
        scope: one of "region", "icb", "cdc_code".
        scope_value: the region name, ICB name, or CDC code to filter by.
        test_code: optional, one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: optional ISO reporting month "YYYY-MM"; leave empty to sum all loaded months.
    """
    payload = analytics_tools.CdcActivityInput(
        scope=scope, scope_value=scope_value, test_code=test_code or None, period_id=period_id or None
    )
    return analytics_tools.analyze_cdc_activity(payload).model_dump()


def find_similar_providers(provider_code: str, test_code: str, period_id: str = "", limit: int = 5) -> dict:
    """Find providers under similar waiting-list pressure to a given provider,
    for the same diagnostic test and reporting period.

    Args:
        provider_code: exact NHS provider organisation code.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month "YYYY-MM". Leave empty for the latest loaded month.
        limit: how many similar providers to return.
    """
    payload = analytics_tools.SimilarProvidersInput(
        provider_code=provider_code, test_code=test_code, period_id=period_id or None, limit=limit
    )
    return analytics_tools.find_similar_providers(payload).model_dump()


def simulate_capacity_change(
    provider_code: str, test_code: str, additional_monthly_activity: int,
    duration_months: int = 6, period_id: str = "",
) -> dict:
    """Run a simplified, explicitly illustrative projection of what an
    increase in monthly activity would do to a provider's waiting list,
    assuming demand stays constant. Always relay the tool's warning that this
    is a simplified model, not a forecast.

    Args:
        provider_code: exact NHS provider organisation code.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        additional_monthly_activity: extra procedures per month to simulate.
        duration_months: months to project forward (max 24).
        period_id: baseline ISO reporting month "YYYY-MM". Leave empty for the latest loaded month.
    """
    payload = analytics_tools.CapacityScenarioInput(
        provider_code=provider_code, test_code=test_code, additional_monthly_activity=additional_monthly_activity,
        duration_months=duration_months, period_id=period_id or None,
    )
    return analytics_tools.simulate_capacity_change(payload).model_dump()


def search_knowledge_base(query: str) -> list[dict]:
    """Search the indexed knowledge base of diagnostic-test definitions,
    metric definitions, methodology notes, and provider profiles. Use this
    for definition, methodology, and explanatory questions - not for
    up-to-the-minute numbers, which should come from the tools above.

    Args:
        query: search query describing what to look for.
    """
    docs = retrieve(query, method="es_hybrid_rerank", num_results=5)
    return [
        {"id": d["id"], "title": d["title"], "abstract": d["abstract"], "document_type": d.get("categories", "")}
        for d in docs
    ]


def retrieve_metric_definition(metric_name: str) -> dict:
    """Look up the precise definition of a metric used in this application
    (for example "bottleneck score" or "pressure proxy").

    Args:
        metric_name: the metric to look up.
    """
    payload = analytics_tools.MetricDefinitionInput(metric_name=metric_name)
    return analytics_tools.retrieve_metric_definition(payload).model_dump()


def build_agent_runner() -> OpenAIChatCompletionsRunner:
    tools = Tools()
    for fn in (
        resolve_provider_code,
        get_provider_profile,
        rank_provider_waits,
        compare_provider_waits,
        analyze_waiting_trend,
        compare_activity_and_waiting,
        analyze_cdc_activity,
        find_similar_providers,
        simulate_capacity_change,
        retrieve_metric_definition,
        search_knowledge_base,
    ):
        tools.add_tool(fn)

    llm_client = OpenAIChatCompletionsClient(model=OPENAI_CHAT_MODEL)
    return OpenAIChatCompletionsRunner(tools=tools, developer_prompt=DEVELOPER_PROMPT, llm_client=llm_client)


def ask_agent(question: str, previous_messages: list | None = None):
    runner = build_agent_runner()
    return runner.loop(question, previous_messages=previous_messages)
