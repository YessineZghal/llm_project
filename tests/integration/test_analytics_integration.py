"""Integration tests for the analytics layer against the real loaded NHS data
(plan.md Step 18: "Integration tests: Database loading. Retrieval. Tool
execution."). Requires app_postgres running with data already ingested -
see agent/PROGRESS.md for the load command. Not run as part of the pure
unit-test suite (tests/unit/), which must work without any live database.
"""

import pytest

from llm_project.analytics.tools import (
    ProviderProfileInput,
    RankProvidersInput,
    ToolError,
    get_provider_profile,
    rank_provider_waits,
)
from llm_project.db.models import get_session
from llm_project.db.nhs_schema import BottleneckScore, Provider, ProviderTestMonthMetric


def _skip_if_no_data():
    session = get_session()
    try:
        if session.query(Provider).count() == 0:
            pytest.skip("no NHS data loaded - run the ingestion pipeline first")
    finally:
        session.close()


class TestGetProviderProfile:
    def test_known_provider_returns_hand_checkable_result(self):
        _skip_if_no_data()
        profile = get_provider_profile(ProviderProfileInput(provider_code="RJ1", test_code="MRI", period_id="2026-05"))
        assert profile.provider_name == "GUY'S AND ST THOMAS' NHS FOUNDATION TRUST"
        # percentage must reconcile with the raw counts it's derived from
        assert profile.percentage_waiting_6_plus_weeks == pytest.approx(
            profile.waiting_6_plus_weeks / profile.total_waiting * 100, abs=0.01
        )
        assert profile.period_id == "2026-05"

    def test_unknown_provider_raises(self):
        _skip_if_no_data()
        with pytest.raises(ToolError, match="unknown provider_code"):
            get_provider_profile(ProviderProfileInput(provider_code="NOTAREALCODE", test_code="MRI"))

    def test_unsupported_test_raises(self):
        _skip_if_no_data()
        with pytest.raises(ToolError, match="unsupported diagnostic test"):
            get_provider_profile(ProviderProfileInput(provider_code="RJ1", test_code="XRAY"))

    def test_defaults_to_latest_period(self):
        _skip_if_no_data()
        profile = get_provider_profile(ProviderProfileInput(provider_code="RJ1", test_code="MRI"))
        assert profile.period_id == "2026-05"  # latest of the 3 loaded months


class TestRankProviderWaits:
    def test_results_are_correctly_sorted(self):
        _skip_if_no_data()
        result = rank_provider_waits(RankProvidersInput(test_code="MRI", limit=10, sort_order="descending"))
        values = [r.value for r in result.results]
        assert values == sorted(values, reverse=True)

    def test_ascending_vs_descending_are_different(self):
        _skip_if_no_data()
        desc = rank_provider_waits(RankProvidersInput(test_code="MRI", limit=1, sort_order="descending"))
        asc = rank_provider_waits(RankProvidersInput(test_code="MRI", limit=1, sort_order="ascending"))
        assert desc.results[0].provider_code != asc.results[0].provider_code

    def test_limit_is_respected(self):
        _skip_if_no_data()
        result = rank_provider_waits(RankProvidersInput(test_code="CT", limit=3))
        assert len(result.results) <= 3

    def test_unsupported_metric_raises(self):
        _skip_if_no_data()
        with pytest.raises(ToolError, match="unsupported metric"):
            rank_provider_waits(RankProvidersInput(test_code="MRI", metric="not_a_real_metric"))


class TestDerivedMetricsInvariants:
    """Sanity checks on data already computed by analytics.metrics against the
    real loaded months - not a recomputation, but a check that what's in the
    database satisfies the invariants the formulas are supposed to guarantee."""

    def test_percentage_within_bounds(self):
        _skip_if_no_data()
        session = get_session()
        try:
            bad = (
                session.query(ProviderTestMonthMetric)
                .filter(
                    (ProviderTestMonthMetric.percentage_waiting_6_plus_weeks < 0)
                    | (ProviderTestMonthMetric.percentage_waiting_6_plus_weeks > 100)
                )
                .count()
            )
            assert bad == 0
        finally:
            session.close()

    def test_bottleneck_scores_within_bounds(self):
        _skip_if_no_data()
        session = get_session()
        try:
            bad = session.query(BottleneckScore).filter(
                (BottleneckScore.score < 0) | (BottleneckScore.score > 100)
            ).count()
            assert bad == 0
        finally:
            session.close()

    def test_three_weighting_scenarios_exist_per_provider_test_period(self):
        _skip_if_no_data()
        session = get_session()
        try:
            row = session.query(BottleneckScore).first()
            scenarios = {
                s.weighting_scenario
                for s in session.query(BottleneckScore).filter_by(
                    provider_code=row.provider_code, test_code=row.test_code, period_id=row.period_id
                )
            }
            assert scenarios == {"balanced", "waiting_focused", "capacity_focused"}
        finally:
            session.close()
