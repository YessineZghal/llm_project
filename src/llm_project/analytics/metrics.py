"""Derived metrics + bottleneck score (plan.md Step 5).

Numbers are computed here in plain Python from the fact tables, never by an
LLM — the analytical-tools layer only reads already-validated rows from
`provider_test_month_metrics` / `bottleneck_scores`. Guards against division
by zero and missing baselines throughout: a genuinely unknown change is
`None` in the database, never a fabricated `0`.
"""

from collections import defaultdict

from sqlalchemy import select

from llm_project.db.models import get_session
from llm_project.db.nhs_schema import (
    BottleneckScore,
    DiagnosticActivityFact,
    DiagnosticWaitingFact,
    ProviderTestMonthMetric,
    ReportingPeriod,
)

PRESSURE_THRESHOLD = 0.0  # pressure_proxy > this counts as a "pressured" month

WEIGHTING_SCENARIOS = {
    "balanced": {
        "long_wait": 0.30, "waiting_growth": 0.25, "activity_imbalance": 0.20,
        "persistence": 0.15, "cdc_indicator": 0.10,
    },
    "waiting_focused": {
        "long_wait": 0.40, "waiting_growth": 0.35, "activity_imbalance": 0.10,
        "persistence": 0.10, "cdc_indicator": 0.05,
    },
    "capacity_focused": {
        "long_wait": 0.20, "waiting_growth": 0.15, "activity_imbalance": 0.35,
        "persistence": 0.10, "cdc_indicator": 0.20,
    },
}

WAITING_6_PLUS_FIELDS = [
    "week_06_07", "week_07_08", "week_08_09", "week_09_10",
    "week_10_11", "week_11_12", "week_12_13", "week_13_plus",
]


def _pct_change(new: float, old: float | None) -> float | None:
    """None (not 0) when the baseline is missing or zero — an undefined
    percentage change is never silently reported as 0%."""
    if old is None or old == 0:
        return None
    return (new - old) / old * 100.0


def compute_provider_test_month_metrics() -> dict:
    session = get_session()
    try:
        waiting_facts = session.execute(select(DiagnosticWaitingFact)).scalars().all()
        activity_by_key = {
            (f.provider_code, f.test_code, f.period_id): f
            for f in session.execute(select(DiagnosticActivityFact)).scalars().all()
        }
        periods = {p.period_id: p for p in session.execute(select(ReportingPeriod)).scalars().all()}

        by_provider_test: dict[tuple[str, str], dict[str, DiagnosticWaitingFact]] = defaultdict(dict)
        for f in waiting_facts:
            by_provider_test[(f.provider_code, f.test_code)][f.period_id] = f

        session.query(ProviderTestMonthMetric).delete()
        session.commit()

        n_written = 0
        for (provider_code, test_code), by_period in by_provider_test.items():
            own_periods = sorted(by_period, key=lambda pid: periods[pid].period_month)
            pressured_months = 0

            for idx, period_id in enumerate(own_periods):
                waiting = by_period[period_id]
                activity = activity_by_key.get((provider_code, test_code, period_id))

                waiting_6_plus = sum(getattr(waiting, f) for f in WAITING_6_PLUS_FIELDS)
                # total_waiting == 0 implies waiting_6_plus == 0 too (a subset) -
                # 0/0 is defined as 0% here by convention, not treated as missing.
                pct_6_plus = (waiting_6_plus / waiting.total_waiting * 100.0) if waiting.total_waiting else 0.0

                total_activity = activity.total_activity if activity else None

                prev_period_id = own_periods[idx - 1] if idx > 0 else None
                prev_waiting = by_period.get(prev_period_id) if prev_period_id else None
                prev_activity = (
                    activity_by_key.get((provider_code, test_code, prev_period_id)) if prev_period_id else None
                )

                waiting_mom = _pct_change(waiting.total_waiting, prev_waiting.total_waiting if prev_waiting else None)
                activity_mom = (
                    _pct_change(total_activity, prev_activity.total_activity)
                    if (total_activity is not None and prev_activity is not None)
                    else None
                )

                # A ~12-month-back comparison isn't available with the current
                # short backfill window (plan.md's own scoped-down MVP months) -
                # left None deliberately rather than computed against the wrong period.
                waiting_yoy = None
                activity_yoy = None

                pressure_proxy = (
                    waiting_mom - activity_mom if (waiting_mom is not None and activity_mom is not None) else None
                )
                if pressure_proxy is not None and pressure_proxy > PRESSURE_THRESHOLD:
                    pressured_months += 1

                quality_flag = "complete" if prev_waiting is not None else "insufficient_history"

                session.add(
                    ProviderTestMonthMetric(
                        provider_code=provider_code,
                        test_code=test_code,
                        period_id=period_id,
                        total_waiting=waiting.total_waiting,
                        waiting_6_plus_weeks=waiting_6_plus,
                        percentage_waiting_6_plus_weeks=round(pct_6_plus, 2),
                        total_activity=total_activity or 0,
                        cdc_activity=None,  # no CDC -> provider mapping yet, see DATA_SOURCES.md
                        waiting_list_monthly_change=waiting_mom,
                        waiting_list_yearly_change=waiting_yoy,
                        activity_monthly_change=activity_mom,
                        activity_yearly_change=activity_yoy,
                        pressure_proxy=pressure_proxy,
                        persistent_pressure_months=pressured_months,
                        quality_flag=quality_flag,
                    )
                )
                n_written += 1

        session.commit()
        return {"provider_test_month_metrics_written": n_written}
    finally:
        session.close()


def _normalize(value: float | None, cohort_values: list[float]) -> float | None:
    """Min-max normalize to 0-100 within the (test, period) cohort. None
    propagates (a provider missing this signal doesn't get a fabricated 0)."""
    if value is None or not cohort_values:
        return None
    lo, hi = min(cohort_values), max(cohort_values)
    if hi == lo:
        return 50.0  # every provider identical on this signal - midpoint, not 0
    return (value - lo) / (hi - lo) * 100.0


def compute_bottleneck_scores() -> dict:
    session = get_session()
    try:
        metrics = session.execute(select(ProviderTestMonthMetric)).scalars().all()

        cohorts: dict[tuple[str, str], list[ProviderTestMonthMetric]] = defaultdict(list)
        for m in metrics:
            cohorts[(m.test_code, m.period_id)].append(m)

        session.query(BottleneckScore).delete()
        session.commit()

        n_written = 0
        for (test_code, period_id), rows in cohorts.items():
            long_wait_vals = [r.percentage_waiting_6_plus_weeks for r in rows]
            growth_vals = [r.waiting_list_monthly_change for r in rows if r.waiting_list_monthly_change is not None]
            persistence_vals = [r.persistent_pressure_months for r in rows]

            imbalance_by_provider: dict[str, float | None] = {}
            for r in rows:
                if r.waiting_list_monthly_change is not None and r.activity_monthly_change is not None:
                    imbalance_by_provider[r.provider_code] = r.waiting_list_monthly_change - r.activity_monthly_change
                else:
                    imbalance_by_provider[r.provider_code] = None
            imbalance_vals = [v for v in imbalance_by_provider.values() if v is not None]

            for r in rows:
                components = {
                    "long_wait": _normalize(r.percentage_waiting_6_plus_weeks, long_wait_vals),
                    "waiting_growth": _normalize(r.waiting_list_monthly_change, growth_vals),
                    "activity_imbalance": _normalize(imbalance_by_provider[r.provider_code], imbalance_vals),
                    "persistence": _normalize(r.persistent_pressure_months, persistence_vals),
                    "cdc_indicator": None,  # no CDC -> provider mapping yet, see DATA_SOURCES.md
                }
                available = {k: v for k, v in components.items() if v is not None}
                if not available:
                    continue

                for scenario_name, weights in WEIGHTING_SCENARIOS.items():
                    total_weight = sum(weights[k] for k in available)
                    score = sum(weights[k] * v for k, v in available.items()) / total_weight

                    session.add(
                        BottleneckScore(
                            provider_code=r.provider_code,
                            test_code=test_code,
                            period_id=period_id,
                            weighting_scenario=scenario_name,
                            score=round(score, 2),
                            component_long_wait=components["long_wait"],
                            component_waiting_growth=components["waiting_growth"],
                            component_activity_imbalance=components["activity_imbalance"],
                            component_persistence=components["persistence"],
                            component_cdc_indicator=components["cdc_indicator"],
                        )
                    )
                    n_written += 1

        session.commit()
        return {"bottleneck_scores_written": n_written}
    finally:
        session.close()


def compute_all() -> dict:
    result = compute_provider_test_month_metrics()
    result.update(compute_bottleneck_scores())
    return result


if __name__ == "__main__":
    print(compute_all())
