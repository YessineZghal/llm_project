"""Controlled analytical tools (plan.md Step 11): typed Pydantic inputs,
parameterized SQL against pre-computed metrics only (never arbitrary SQL,
never an LLM-computed number), allowlisted test codes/metrics, and every
response carries its source period and data-quality warnings.

All 9 of plan.md's tools are implemented here (find_similar_providers,
listed as a phase-two feature in plan.md, is included in a minimal form
since it required no new infrastructure beyond what compare_provider_waits
already needed).
"""

import time
from typing import Literal

from pydantic import BaseModel, Field

from llm_project.db.models import get_session
from llm_project.db.nhs_schema import BottleneckScore, CdcActivityFact, Provider, ProviderTestMonthMetric, ReportingPeriod

ALLOWED_TEST_CODES = {"MRI", "CT", "NON_OBSTETRIC_ULTRASOUND", "COLONOSCOPY"}
ALLOWED_WEIGHTING_SCENARIOS = {"balanced", "waiting_focused", "capacity_focused"}
ALLOWED_RANK_METRICS = {
    "percentage_waiting_6_plus_weeks",
    "total_waiting",
    "waiting_list_monthly_change",
    "pressure_proxy",
    "persistent_pressure_months",
}
MAX_RANK_LIMIT = 25

SOURCE_NOTE = (
    "src/llm_project/analytics/metrics.py -> provider_test_month_metrics "
    "(computed from NHS DM01 data; see DATA_SOURCES.md)"
)


class ToolError(Exception):
    """Raised for invalid input or missing data - never silently swallowed."""


def _validate_test_code(test_code: str) -> str:
    test_code = test_code.upper().strip()
    if test_code not in ALLOWED_TEST_CODES:
        raise ToolError(f"unsupported diagnostic test {test_code!r}; supported: {sorted(ALLOWED_TEST_CODES)}")
    return test_code


def _latest_period_id(session) -> str:
    period = session.query(ReportingPeriod).order_by(ReportingPeriod.period_month.desc()).first()
    if period is None:
        raise ToolError("no reporting periods loaded")
    return period.period_id


# --- get_provider_profile --------------------------------------------------


class ProviderProfileInput(BaseModel):
    provider_code: str
    test_code: str
    period_id: str | None = None  # defaults to the latest loaded period


class ProviderProfileResult(BaseModel):
    provider_code: str
    provider_name: str
    test_code: str
    period_id: str
    total_waiting: int
    waiting_6_plus_weeks: int
    percentage_waiting_6_plus_weeks: float
    total_activity: int
    waiting_list_monthly_change_pct: float | None
    activity_monthly_change_pct: float | None
    pressure_proxy: float | None
    persistent_pressure_months: int
    quality_flag: str
    warnings: list[str]
    source: str = SOURCE_NOTE
    execution_time_ms: float


def get_provider_profile(payload: ProviderProfileInput) -> ProviderProfileResult:
    """Args:
        provider_code: NHS provider organisation code (e.g. "RJ1").
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month "YYYY-MM"; defaults to the latest loaded month.
    """
    start = time.perf_counter()
    session = get_session()
    try:
        test_code = _validate_test_code(payload.test_code)
        provider = session.get(Provider, payload.provider_code)
        if provider is None:
            raise ToolError(f"unknown provider_code {payload.provider_code!r}")

        period_id = payload.period_id or _latest_period_id(session)

        metric = (
            session.query(ProviderTestMonthMetric)
            .filter_by(provider_code=payload.provider_code, test_code=test_code, period_id=period_id)
            .first()
        )
        if metric is None:
            raise ToolError(
                f"no data for provider {payload.provider_code!r}, test {test_code!r}, period {period_id!r}"
            )

        warnings = []
        if metric.quality_flag != "complete":
            warnings.append("insufficient prior-month history for month-over-month comparison")
        if metric.cdc_activity is None:
            warnings.append("CDC activity not available (no CDC-to-provider mapping yet, see DATA_SOURCES.md)")

        return ProviderProfileResult(
            provider_code=provider.provider_code,
            provider_name=provider.provider_name,
            test_code=test_code,
            period_id=period_id,
            total_waiting=metric.total_waiting,
            waiting_6_plus_weeks=metric.waiting_6_plus_weeks,
            percentage_waiting_6_plus_weeks=metric.percentage_waiting_6_plus_weeks,
            total_activity=metric.total_activity,
            waiting_list_monthly_change_pct=metric.waiting_list_monthly_change,
            activity_monthly_change_pct=metric.activity_monthly_change,
            pressure_proxy=metric.pressure_proxy,
            persistent_pressure_months=metric.persistent_pressure_months,
            quality_flag=metric.quality_flag,
            warnings=warnings,
            execution_time_ms=(time.perf_counter() - start) * 1000,
        )
    finally:
        session.close()


# --- rank_provider_waits -----------------------------------------------------


class RankProvidersInput(BaseModel):
    test_code: str
    period_id: str | None = None
    metric: str = "percentage_waiting_6_plus_weeks"
    sort_order: Literal["ascending", "descending"] = "descending"
    limit: int = Field(default=5, ge=1, le=MAX_RANK_LIMIT)


class RankedProvider(BaseModel):
    provider_code: str
    provider_name: str
    value: float | int | None


class RankProvidersResult(BaseModel):
    test_code: str
    period_id: str
    metric: str
    sort_order: str
    results: list[RankedProvider]
    warnings: list[str]
    source: str = SOURCE_NOTE
    execution_time_ms: float


def rank_provider_waits(payload: RankProvidersInput) -> RankProvidersResult:
    """Args:
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month "YYYY-MM"; defaults to the latest loaded month.
        metric: one of percentage_waiting_6_plus_weeks, total_waiting,
            waiting_list_monthly_change, pressure_proxy, persistent_pressure_months.
        sort_order: "ascending" or "descending".
        limit: number of providers to return (max 25).
    """
    start = time.perf_counter()
    session = get_session()
    try:
        test_code = _validate_test_code(payload.test_code)
        if payload.metric not in ALLOWED_RANK_METRICS:
            raise ToolError(f"unsupported metric {payload.metric!r}; supported: {sorted(ALLOWED_RANK_METRICS)}")

        period_id = payload.period_id or _latest_period_id(session)
        column = getattr(ProviderTestMonthMetric, payload.metric)

        query = (
            session.query(ProviderTestMonthMetric, Provider.provider_name)
            .join(Provider, Provider.provider_code == ProviderTestMonthMetric.provider_code)
            .filter(ProviderTestMonthMetric.test_code == test_code, ProviderTestMonthMetric.period_id == period_id)
            .filter(column.isnot(None))
        )
        query = query.order_by(column.desc() if payload.sort_order == "descending" else column.asc())
        rows = query.limit(payload.limit).all()

        warnings = []
        if not rows:
            warnings.append("no providers had a non-null value for this metric/period")

        results = [
            RankedProvider(provider_code=m.provider_code, provider_name=name, value=getattr(m, payload.metric))
            for m, name in rows
        ]

        return RankProvidersResult(
            test_code=test_code,
            period_id=period_id,
            metric=payload.metric,
            sort_order=payload.sort_order,
            results=results,
            warnings=warnings,
            execution_time_ms=(time.perf_counter() - start) * 1000,
        )
    finally:
        session.close()


# --- compare_provider_waits --------------------------------------------------


class CompareProvidersInput(BaseModel):
    provider_codes: list[str] = Field(min_length=2, max_length=5)
    test_code: str
    period_id: str | None = None


class ProviderComparisonEntry(BaseModel):
    provider_code: str
    provider_name: str
    total_waiting: int
    percentage_waiting_6_plus_weeks: float
    total_activity: int
    pressure_proxy: float | None


class CompareProvidersResult(BaseModel):
    test_code: str
    period_id: str
    entries: list[ProviderComparisonEntry]
    warnings: list[str]
    source: str = SOURCE_NOTE
    execution_time_ms: float


def compare_provider_waits(payload: CompareProvidersInput) -> CompareProvidersResult:
    """Args:
        provider_codes: 2 to 5 NHS provider organisation codes.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month "YYYY-MM"; defaults to the latest loaded month.
            All providers are compared on the same period, per plan.md Step 15.
    """
    start = time.perf_counter()
    session = get_session()
    try:
        test_code = _validate_test_code(payload.test_code)
        period_id = payload.period_id or _latest_period_id(session)

        entries, warnings = [], []
        for code in payload.provider_codes:
            provider = session.get(Provider, code)
            if provider is None:
                warnings.append(f"unknown provider_code {code!r}, skipped")
                continue
            metric = (
                session.query(ProviderTestMonthMetric)
                .filter_by(provider_code=code, test_code=test_code, period_id=period_id)
                .first()
            )
            if metric is None:
                warnings.append(f"no data for provider {code!r} in {test_code!r}/{period_id!r}, skipped")
                continue
            entries.append(
                ProviderComparisonEntry(
                    provider_code=code,
                    provider_name=provider.provider_name,
                    total_waiting=metric.total_waiting,
                    percentage_waiting_6_plus_weeks=metric.percentage_waiting_6_plus_weeks,
                    total_activity=metric.total_activity,
                    pressure_proxy=metric.pressure_proxy,
                )
            )

        if len(entries) < 2:
            raise ToolError("fewer than 2 providers had usable data for this test/period; cannot compare")

        return CompareProvidersResult(
            test_code=test_code, period_id=period_id, entries=entries, warnings=warnings,
            execution_time_ms=(time.perf_counter() - start) * 1000,
        )
    finally:
        session.close()


# --- analyze_waiting_trend ---------------------------------------------------


TREND_METRICS = {"total_waiting", "percentage_waiting_6_plus_weeks", "total_activity"}


class WaitingTrendInput(BaseModel):
    provider_code: str
    test_code: str
    metric: str = "percentage_waiting_6_plus_weeks"


class TrendPoint(BaseModel):
    period_id: str
    value: float | int


class WaitingTrendResult(BaseModel):
    provider_code: str
    provider_name: str
    test_code: str
    metric: str
    points: list[TrendPoint]
    direction: Literal["increasing", "decreasing", "stable", "insufficient_data"]
    warnings: list[str]
    source: str = SOURCE_NOTE
    execution_time_ms: float


def analyze_waiting_trend(payload: WaitingTrendInput) -> WaitingTrendResult:
    """Args:
        provider_code: NHS provider organisation code.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        metric: one of total_waiting, percentage_waiting_6_plus_weeks, total_activity.
    Returns every loaded reporting month for this provider/test, in order
    (plan.md sample question 2: "Show the MRI long-wait trend for a
    selected provider over the latest complete months").
    """
    start = time.perf_counter()
    session = get_session()
    try:
        test_code = _validate_test_code(payload.test_code)
        if payload.metric not in TREND_METRICS:
            raise ToolError(f"unsupported metric {payload.metric!r}; supported: {sorted(TREND_METRICS)}")

        provider = session.get(Provider, payload.provider_code)
        if provider is None:
            raise ToolError(f"unknown provider_code {payload.provider_code!r}")

        periods = {p.period_id: p for p in session.query(ReportingPeriod).all()}
        rows = (
            session.query(ProviderTestMonthMetric)
            .filter_by(provider_code=payload.provider_code, test_code=test_code)
            .all()
        )
        if not rows:
            raise ToolError(f"no data for provider {payload.provider_code!r}, test {test_code!r}")

        rows.sort(key=lambda r: periods[r.period_id].period_month)
        points = [TrendPoint(period_id=r.period_id, value=getattr(r, payload.metric)) for r in rows]

        warnings = []
        if len(points) < 2:
            direction = "insufficient_data"
            warnings.append("only one reporting month loaded for this provider/test; no trend direction possible")
        else:
            delta = points[-1].value - points[0].value
            direction = "stable" if abs(delta) < 1e-9 else ("increasing" if delta > 0 else "decreasing")

        return WaitingTrendResult(
            provider_code=provider.provider_code, provider_name=provider.provider_name, test_code=test_code,
            metric=payload.metric, points=points, direction=direction, warnings=warnings,
            execution_time_ms=(time.perf_counter() - start) * 1000,
        )
    finally:
        session.close()


# --- compare_activity_and_waiting --------------------------------------------


class ActivityVsWaitingInput(BaseModel):
    provider_code: str
    test_code: str
    period_id: str | None = None


class ActivityVsWaitingResult(BaseModel):
    provider_code: str
    provider_name: str
    test_code: str
    period_id: str
    waiting_list_monthly_change_pct: float | None
    activity_monthly_change_pct: float | None
    verdict: Literal[
        "activity_grew_faster", "waiting_list_grew_faster", "roughly_equal", "insufficient_data"
    ]
    warnings: list[str]
    source: str = SOURCE_NOTE
    execution_time_ms: float


def compare_activity_and_waiting(payload: ActivityVsWaitingInput) -> ActivityVsWaitingResult:
    """Args:
        provider_code: NHS provider organisation code.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month "YYYY-MM"; defaults to the latest loaded month.
    Answers plan.md sample question 6: "Did activity grow faster or slower
    than the waiting list for a selected provider?"
    """
    start = time.perf_counter()
    session = get_session()
    try:
        test_code = _validate_test_code(payload.test_code)
        provider = session.get(Provider, payload.provider_code)
        if provider is None:
            raise ToolError(f"unknown provider_code {payload.provider_code!r}")

        period_id = payload.period_id or _latest_period_id(session)
        metric = (
            session.query(ProviderTestMonthMetric)
            .filter_by(provider_code=payload.provider_code, test_code=test_code, period_id=period_id)
            .first()
        )
        if metric is None:
            raise ToolError(f"no data for provider {payload.provider_code!r}, test {test_code!r}, period {period_id!r}")

        warnings = []
        wlc, ac = metric.waiting_list_monthly_change, metric.activity_monthly_change
        if wlc is None or ac is None:
            verdict = "insufficient_data"
            warnings.append("insufficient prior-month history for month-over-month comparison")
        elif abs(wlc - ac) < 1.0:
            verdict = "roughly_equal"
        elif ac > wlc:
            verdict = "activity_grew_faster"
        else:
            verdict = "waiting_list_grew_faster"

        return ActivityVsWaitingResult(
            provider_code=provider.provider_code, provider_name=provider.provider_name, test_code=test_code,
            period_id=period_id, waiting_list_monthly_change_pct=wlc, activity_monthly_change_pct=ac,
            verdict=verdict, warnings=warnings, execution_time_ms=(time.perf_counter() - start) * 1000,
        )
    finally:
        session.close()


# --- analyze_cdc_activity ----------------------------------------------------


class CdcActivityInput(BaseModel):
    scope: Literal["region", "icb", "cdc_code"]
    scope_value: str
    test_code: str | None = None
    period_id: str | None = None


class CdcActivityResult(BaseModel):
    scope: str
    scope_value: str
    test_code: str | None
    period_id: str | None
    total_activity: int
    centres_included: list[str]
    warnings: list[str]
    source: str = "cdc_activity_facts (computed from NHS CDC data; see DATA_SOURCES.md)"
    execution_time_ms: float


def analyze_cdc_activity(payload: CdcActivityInput) -> CdcActivityResult:
    """Args:
        scope: "region", "icb", or "cdc_code" - CDC activity has no provider
            mapping yet (see DATA_SOURCES.md), so it can only be queried by
            these dimensions, never by provider_code.
        scope_value: the region name, ICB name, or CDC code to filter by.
        test_code: optional, one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: optional ISO reporting month; if omitted, sums across all loaded months.
    """
    start = time.perf_counter()
    session = get_session()
    try:
        query = session.query(CdcActivityFact)
        if payload.scope == "region":
            query = query.filter(CdcActivityFact.region_name == payload.scope_value)
        elif payload.scope == "icb":
            query = query.filter(CdcActivityFact.icb == payload.scope_value)
        else:
            query = query.filter(CdcActivityFact.cdc_code == payload.scope_value)

        test_code = None
        if payload.test_code:
            test_code = _validate_test_code(payload.test_code)
            query = query.filter(CdcActivityFact.test_code == test_code)
        if payload.period_id:
            query = query.filter(CdcActivityFact.period_id == payload.period_id)

        rows = query.all()
        warnings = ["CDC activity cannot be linked to a specific NHS provider (no mapping available yet)"]
        if not rows:
            warnings.append(f"no CDC activity found for {payload.scope}={payload.scope_value!r}")

        return CdcActivityResult(
            scope=payload.scope, scope_value=payload.scope_value, test_code=test_code, period_id=payload.period_id,
            total_activity=sum(r.activity_count for r in rows), centres_included=sorted({r.cdc_name for r in rows}),
            warnings=warnings, execution_time_ms=(time.perf_counter() - start) * 1000,
        )
    finally:
        session.close()


# --- find_similar_providers (phase-two in plan.md, minimal version) ---------


class SimilarProvidersInput(BaseModel):
    provider_code: str
    test_code: str
    period_id: str | None = None
    limit: int = Field(default=5, ge=1, le=MAX_RANK_LIMIT)


class SimilarProvider(BaseModel):
    provider_code: str
    provider_name: str
    percentage_waiting_6_plus_weeks: float
    distance: float


class SimilarProvidersResult(BaseModel):
    provider_code: str
    test_code: str
    period_id: str
    results: list[SimilarProvider]
    warnings: list[str]
    source: str = SOURCE_NOTE
    execution_time_ms: float


def find_similar_providers(payload: SimilarProvidersInput) -> SimilarProvidersResult:
    """Args:
        provider_code: NHS provider organisation code to find similar providers for.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month; defaults to the latest loaded month.
        limit: number of similar providers to return.
    Similarity is nearest-neighbour on percentage_waiting_6_plus_weeks
    within the same test and period - a simple, transparent notion of
    "under similar pressure", not a learned embedding.
    """
    start = time.perf_counter()
    session = get_session()
    try:
        test_code = _validate_test_code(payload.test_code)
        period_id = payload.period_id or _latest_period_id(session)

        target = (
            session.query(ProviderTestMonthMetric)
            .filter_by(provider_code=payload.provider_code, test_code=test_code, period_id=period_id)
            .first()
        )
        if target is None:
            raise ToolError(f"no data for provider {payload.provider_code!r}, test {test_code!r}, period {period_id!r}")

        rows = (
            session.query(ProviderTestMonthMetric, Provider.provider_name)
            .join(Provider, Provider.provider_code == ProviderTestMonthMetric.provider_code)
            .filter(
                ProviderTestMonthMetric.test_code == test_code,
                ProviderTestMonthMetric.period_id == period_id,
                ProviderTestMonthMetric.provider_code != payload.provider_code,
            )
            .all()
        )
        scored = sorted(
            (
                (abs(m.percentage_waiting_6_plus_weeks - target.percentage_waiting_6_plus_weeks), m, name)
                for m, name in rows
            ),
            key=lambda t: t[0],
        )[: payload.limit]

        results = [
            SimilarProvider(
                provider_code=m.provider_code, provider_name=name,
                percentage_waiting_6_plus_weeks=m.percentage_waiting_6_plus_weeks, distance=round(dist, 2),
            )
            for dist, m, name in scored
        ]

        return SimilarProvidersResult(
            provider_code=payload.provider_code, test_code=test_code, period_id=period_id, results=results,
            warnings=[], execution_time_ms=(time.perf_counter() - start) * 1000,
        )
    finally:
        session.close()


# --- simulate_capacity_change ------------------------------------------------


class CapacityScenarioInput(BaseModel):
    provider_code: str
    test_code: str
    additional_monthly_activity: int
    duration_months: int = Field(default=6, ge=1, le=24)
    period_id: str | None = None


class CapacityScenarioPoint(BaseModel):
    month: int
    projected_waiting_list: int


class CapacityScenarioResult(BaseModel):
    provider_code: str
    provider_name: str
    test_code: str
    baseline_period_id: str
    baseline_waiting_list: int
    implied_monthly_demand: int
    baseline_monthly_activity: int
    additional_monthly_activity: int
    projection: list[CapacityScenarioPoint]
    warning: str = (
        "This is a simplified linear projection for illustration only, not a forecast. It assumes "
        "monthly demand stays constant at the level implied by recent data and does not account for "
        "seasonality, referral changes, staffing, or any other real-world factor."
    )
    warnings: list[str]
    source: str = SOURCE_NOTE
    execution_time_ms: float


def simulate_capacity_change(payload: CapacityScenarioInput) -> CapacityScenarioResult:
    """Args:
        provider_code: NHS provider organisation code.
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        additional_monthly_activity: extra procedures per month to simulate (plan.md sample question 10).
        duration_months: how many months to project forward (max 24).
        period_id: baseline reporting month; defaults to the latest loaded month.
    Explicitly a simplified illustrative model (plan.md Step 15's Capacity
    Scenario page requirement), not a prediction - see the returned warning.
    """
    start = time.perf_counter()
    session = get_session()
    try:
        test_code = _validate_test_code(payload.test_code)
        provider = session.get(Provider, payload.provider_code)
        if provider is None:
            raise ToolError(f"unknown provider_code {payload.provider_code!r}")

        period_id = payload.period_id or _latest_period_id(session)
        current = (
            session.query(ProviderTestMonthMetric)
            .filter_by(provider_code=payload.provider_code, test_code=test_code, period_id=period_id)
            .first()
        )
        if current is None:
            raise ToolError(f"no data for provider {payload.provider_code!r}, test {test_code!r}, period {period_id!r}")

        warnings = []
        # implied demand = activity + change in waiting list (since
        # Δwaiting_list = demand - activity in a simple monthly balance)
        if current.waiting_list_monthly_change is not None:
            prev_waiting = current.total_waiting / (1 + current.waiting_list_monthly_change / 100)
            delta_waiting = current.total_waiting - prev_waiting
            implied_demand = round(current.total_activity + delta_waiting)
        else:
            implied_demand = current.total_activity
            warnings.append("no prior-month data - assumed demand equals current activity (steady state)")

        new_capacity = current.total_activity + payload.additional_monthly_activity
        projection = []
        waiting_list = current.total_waiting
        for month in range(1, payload.duration_months + 1):
            waiting_list = max(0, waiting_list + implied_demand - new_capacity)
            projection.append(CapacityScenarioPoint(month=month, projected_waiting_list=waiting_list))

        return CapacityScenarioResult(
            provider_code=provider.provider_code, provider_name=provider.provider_name, test_code=test_code,
            baseline_period_id=period_id, baseline_waiting_list=current.total_waiting,
            implied_monthly_demand=implied_demand, baseline_monthly_activity=current.total_activity,
            additional_monthly_activity=payload.additional_monthly_activity, projection=projection,
            warnings=warnings, execution_time_ms=(time.perf_counter() - start) * 1000,
        )
    finally:
        session.close()


# --- retrieve_metric_definition (bridges to the RAG layer) ------------------


class MetricDefinitionInput(BaseModel):
    metric_name: str


class MetricDefinitionResult(BaseModel):
    metric_name: str
    definition: str | None
    document_id: str | None
    warnings: list[str]
    source: str = "src/llm_project/search/retriever.py -> metric_definition documents"
    execution_time_ms: float


def retrieve_metric_definition(payload: MetricDefinitionInput) -> MetricDefinitionResult:
    """Args:
        metric_name: free-text name of the metric to look up, e.g. "bottleneck score"
            or "waiting six weeks or longer".
    The only tool that calls the RAG retrieval layer rather than SQL directly -
    metric definitions are reference text, not computed facts.
    """
    start = time.perf_counter()
    from llm_project.search.retriever import retrieve

    candidates = retrieve(payload.metric_name, method="es_hybrid_rerank", num_results=10)
    matches = [d for d in candidates if d.get("categories") == "metric_definition"]

    warnings = []
    if not matches:
        warnings.append("no metric_definition document matched this query closely")
        return MetricDefinitionResult(
            metric_name=payload.metric_name, definition=None, document_id=None, warnings=warnings,
            execution_time_ms=(time.perf_counter() - start) * 1000,
        )

    best = matches[0]
    return MetricDefinitionResult(
        metric_name=payload.metric_name, definition=best["abstract"], document_id=best["id"], warnings=warnings,
        execution_time_ms=(time.perf_counter() - start) * 1000,
    )


# --- get_bottleneck_ranking --------------------------------------------------


class BottleneckRankingInput(BaseModel):
    test_code: str
    period_id: str | None = None
    weighting_scenario: str = "balanced"
    limit: int = Field(default=10, ge=1, le=MAX_RANK_LIMIT)
    min_quality: Literal["any", "complete_only"] = "any"


class BottleneckRankingEntry(BaseModel):
    provider_code: str
    provider_name: str
    score: float
    component_long_wait: float
    component_waiting_growth: float | None
    component_activity_imbalance: float | None
    component_persistence: float | None
    component_cdc_indicator: float | None
    quality_flag: str


class BottleneckRankingResult(BaseModel):
    test_code: str
    period_id: str
    weighting_scenario: str
    results: list[BottleneckRankingEntry]
    warnings: list[str]
    source: str = (
        "src/llm_project/analytics/metrics.py -> bottleneck_scores "
        "(project-specific indicator, not an official NHS metric; see DATA_SOURCES.md)"
    )
    execution_time_ms: float


def get_bottleneck_ranking(payload: BottleneckRankingInput) -> BottleneckRankingResult:
    """Args:
        test_code: one of MRI, CT, NON_OBSTETRIC_ULTRASOUND, COLONOSCOPY.
        period_id: ISO reporting month "YYYY-MM"; defaults to the latest loaded month.
        weighting_scenario: one of balanced, waiting_focused, capacity_focused -
            the same components weighted differently, not different data.
        limit: how many providers to return (max 25).
        min_quality: "complete_only" restricts to providers with full prior-month
            history (quality_flag == "complete" in the underlying metrics), for a
            stricter comparison; "any" includes providers with partial history.
    The bottleneck score is a project-specific indicator for relative comparison
    within the same test and period, not an official NHS measure.
    """
    start = time.perf_counter()
    session = get_session()
    try:
        test_code = _validate_test_code(payload.test_code)
        if payload.weighting_scenario not in ALLOWED_WEIGHTING_SCENARIOS:
            raise ToolError(
                f"unsupported weighting_scenario {payload.weighting_scenario!r}; "
                f"supported: {sorted(ALLOWED_WEIGHTING_SCENARIOS)}"
            )
        period_id = payload.period_id or _latest_period_id(session)

        query = (
            session.query(BottleneckScore, Provider.provider_name, ProviderTestMonthMetric.quality_flag)
            .join(Provider, Provider.provider_code == BottleneckScore.provider_code)
            .join(
                ProviderTestMonthMetric,
                (ProviderTestMonthMetric.provider_code == BottleneckScore.provider_code)
                & (ProviderTestMonthMetric.test_code == BottleneckScore.test_code)
                & (ProviderTestMonthMetric.period_id == BottleneckScore.period_id),
            )
            .filter(
                BottleneckScore.test_code == test_code,
                BottleneckScore.period_id == period_id,
                BottleneckScore.weighting_scenario == payload.weighting_scenario,
            )
        )
        if payload.min_quality == "complete_only":
            query = query.filter(ProviderTestMonthMetric.quality_flag == "complete")

        rows = query.order_by(BottleneckScore.score.desc()).limit(payload.limit).all()

        warnings = ["the bottleneck score is a project-specific indicator, not an official NHS metric"]
        if not rows:
            warnings.append("no providers matched this test/period/quality filter")

        results = [
            BottleneckRankingEntry(
                provider_code=b.provider_code,
                provider_name=name,
                score=b.score,
                component_long_wait=b.component_long_wait,
                component_waiting_growth=b.component_waiting_growth,
                component_activity_imbalance=b.component_activity_imbalance,
                component_persistence=b.component_persistence,
                component_cdc_indicator=b.component_cdc_indicator,
                quality_flag=quality_flag,
            )
            for b, name, quality_flag in rows
        ]

        return BottleneckRankingResult(
            test_code=test_code, period_id=period_id, weighting_scenario=payload.weighting_scenario,
            results=results, warnings=warnings, execution_time_ms=(time.perf_counter() - start) * 1000,
        )
    finally:
        session.close()
