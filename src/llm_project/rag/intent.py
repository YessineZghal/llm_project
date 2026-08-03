"""Query rewriting and intent classification (plan.md Step 10): converts a
natural-language question into a typed, Pydantic-validated set of parameters
before any tool is called. The LLM is used only for language understanding
(which intent, which entities were mentioned); resolving those mentions
against real providers/tests/metrics is done in code against the database
and fixed allowlists, never trusted blindly from the LLM (plan.md failure
controls: "reject unknown metrics", "resolve ambiguous provider names
visibly", "do not guess missing scenario parameters").
"""

import json
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from llm_project.analytics.tools import ALLOWED_RANK_METRICS, ALLOWED_TEST_CODES
from llm_project.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL
from llm_project.db.models import get_session
from llm_project.db.nhs_schema import Provider

Intent = Literal[
    "definition_lookup",
    "provider_profile",
    "compare_providers",
    "rank_providers",
    "trend_analysis",
    "cdc_analysis",
    "capacity_scenario",
    "methodology_question",
    "unsupported_medical_request",
]

INTENTS: tuple[str, ...] = (
    "definition_lookup", "provider_profile", "compare_providers", "rank_providers",
    "trend_analysis", "cdc_analysis", "capacity_scenario", "methodology_question",
    "unsupported_medical_request",
)


class ExtractedQuery(BaseModel):
    intent: Intent
    provider_mentions: list[str] = []  # raw text as mentioned, not yet resolved
    diagnostic_test_mention: str | None = None
    metric_mention: str | None = None
    date_mention: str | None = None
    limit: int | None = None
    sort_order: Literal["ascending", "descending"] | None = None
    raw_question: str


CLASSIFY_PROMPT = """
You classify questions for an NHS diagnostic waiting-time application. Extract the
intent and any entities mentioned, without resolving them to exact database values -
just report what the user said.

Intents (choose exactly one):
- definition_lookup: asking what a term or metric means
- provider_profile: asking about one specific provider's waiting/activity figures
- compare_providers: asking to compare two or more named providers
- rank_providers: asking which providers rank highest/lowest on some measure
- trend_analysis: asking how one provider's figures changed over time
- cdc_analysis: asking about Community Diagnostic Centre activity
- capacity_scenario: asking what would happen under a hypothetical capacity change
- methodology_question: asking about data sources, methodology, or limitations
- unsupported_medical_request: asking for individual clinical advice, diagnosis,
  personal wait-time prediction, or anything about a specific patient

Diagnostic tests in scope: MRI, CT, non-obstetric ultrasound, colonoscopy.

Question: {question}

Return ONLY a JSON object of the exact form:
{{
  "intent": "<one of the intents above>",
  "provider_mentions": ["<provider names or codes as mentioned, if any>"],
  "diagnostic_test_mention": "<test as mentioned, or null>",
  "metric_mention": "<metric as mentioned, or null>",
  "date_mention": "<date/period as mentioned, or null>",
  "limit": <number mentioned for a ranking, or null>,
  "sort_order": "<ascending, descending, or null>"
}}
""".strip()


def classify_intent(question: str, client: OpenAI | None = None) -> ExtractedQuery:
    client = client or OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(question=question)}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content or "{}")
    if data.get("intent") not in INTENTS:
        data["intent"] = "definition_lookup"  # safest fallback: routes to RAG, not a tool with bad args
    data["raw_question"] = question
    return ExtractedQuery(**data)


class ProviderResolution(BaseModel):
    status: Literal["resolved", "ambiguous", "not_found"]
    provider_code: str | None = None
    provider_name: str | None = None
    candidates: list[str] = []  # provider names, when ambiguous - resolved visibly, not guessed


def resolve_provider(mention: str) -> ProviderResolution:
    """Resolve a raw provider mention against real providers. Exact code match
    first; otherwise case-insensitive substring match on name, surfacing all
    matches when there is more than one rather than silently picking one."""
    session = get_session()
    try:
        exact = session.get(Provider, mention.strip().upper())
        if exact is not None:
            return ProviderResolution(status="resolved", provider_code=exact.provider_code, provider_name=exact.provider_name)

        needle = mention.strip().lower()
        matches = session.query(Provider).filter(Provider.provider_name.ilike(f"%{needle}%")).limit(10).all()
        if len(matches) == 1:
            m = matches[0]
            return ProviderResolution(status="resolved", provider_code=m.provider_code, provider_name=m.provider_name)
        if len(matches) > 1:
            return ProviderResolution(status="ambiguous", candidates=[m.provider_name for m in matches])
        return ProviderResolution(status="not_found")
    finally:
        session.close()


def resolve_test(mention: str | None) -> str | None:
    """Resolve a raw test mention to an allowlisted test code, or None if it
    doesn't match a supported test - never guessed, never defaulted."""
    if not mention:
        return None
    normalized = mention.strip().upper().replace(" ", "_").replace("-", "_")
    if normalized in ALLOWED_TEST_CODES:
        return normalized
    aliases = {
        "MAGNETIC_RESONANCE_IMAGING": "MRI",
        "COMPUTED_TOMOGRAPHY": "CT",
        "ULTRASOUND": "NON_OBSTETRIC_ULTRASOUND",
        "NON_OBSTETRIC_ULTRASOUND_SCAN": "NON_OBSTETRIC_ULTRASOUND",
    }
    return aliases.get(normalized)


def resolve_metric(mention: str | None) -> str | None:
    if not mention:
        return None
    normalized = mention.strip().lower().replace(" ", "_")
    for m in ALLOWED_RANK_METRICS:
        if normalized in m or m in normalized:
            return m
    return None
