"""Controlled analytical tools (plan.md Step 11): typed Pydantic inputs,
parameterized SQL against pre-computed metrics only (never arbitrary SQL,
never an LLM-computed number), allowlisted test codes/metrics, and every
response carries its source period and data-quality warnings.

First 2 of the plan's 9 tools — enough for Milestone 3's vertical slice
(plan.md's own first example question: "Which providers have the highest
MRI long-wait rates?"). The remaining 7 land with the agent in Milestone 5.
"""

import time
from typing import Literal

from pydantic import BaseModel, Field

from llm_project.db.models import get_session
from llm_project.db.nhs_schema import Provider, ProviderTestMonthMetric, ReportingPeriod

ALLOWED_TEST_CODES = {"MRI", "CT", "NON_OBSTETRIC_ULTRASOUND", "COLONOSCOPY"}
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
