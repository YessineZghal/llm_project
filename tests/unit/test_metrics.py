"""Unit tests for the derived-metric formulas (plan.md Step 5: "every formula
has a test" with hand-calculated examples). Pure-function tests only, no
database access - see tests/integration/ for the full pipeline against real
loaded data.
"""

import pytest

from llm_project.analytics.metrics import _normalize, _pct_change


class TestPctChange:
    def test_normal_increase(self):
        assert _pct_change(110, 100) == pytest.approx(10.0)

    def test_normal_decrease(self):
        assert _pct_change(90, 100) == pytest.approx(-10.0)

    def test_hand_calculated_example(self):
        # East Kent Hospitals MRI, April -> May 2026 waiting list: 12198 -> 12455
        assert _pct_change(12455, 12198) == pytest.approx(2.1067, abs=1e-3)

    def test_none_when_baseline_zero(self):
        assert _pct_change(50, 0) is None

    def test_none_when_baseline_missing(self):
        assert _pct_change(50, None) is None

    def test_zero_change(self):
        assert _pct_change(100, 100) == pytest.approx(0.0)


class TestNormalize:
    def test_normal_min_max(self):
        assert _normalize(50, [0, 50, 100]) == pytest.approx(50.0)
        assert _normalize(0, [0, 50, 100]) == pytest.approx(0.0)
        assert _normalize(100, [0, 50, 100]) == pytest.approx(100.0)

    def test_none_value_propagates(self):
        assert _normalize(None, [0, 50, 100]) is None

    def test_empty_cohort_returns_none(self):
        assert _normalize(50, []) is None

    def test_no_spread_returns_midpoint_not_zero(self):
        # every provider identical on this signal - midpoint, not a fabricated 0
        assert _normalize(42, [42, 42, 42]) == pytest.approx(50.0)

    def test_value_below_cohort_min_still_computes(self):
        # a value equal to the minimum normalizes to 0, not negative or None
        assert _normalize(10, [10, 20, 30]) == pytest.approx(0.0)
