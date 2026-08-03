"""Unit tests for analytical-tool input validation (plan.md Step 11:
"no tool accepts arbitrary SQL" / allowlisted metrics and test codes).
Pure validation logic only, no database access.
"""

import pytest

from llm_project.analytics.tools import ALLOWED_RANK_METRICS, ALLOWED_TEST_CODES, ToolError, _validate_test_code


class TestValidateTestCode:
    @pytest.mark.parametrize("code", sorted(ALLOWED_TEST_CODES))
    def test_allowed_codes_pass_through(self, code):
        assert _validate_test_code(code) == code

    def test_lowercase_is_normalized(self):
        assert _validate_test_code("mri") == "MRI"

    def test_whitespace_is_stripped(self):
        assert _validate_test_code("  MRI  ") == "MRI"

    def test_unsupported_code_raises(self):
        with pytest.raises(ToolError, match="unsupported diagnostic test"):
            _validate_test_code("XRAY")

    def test_sql_injection_attempt_raises_not_executes(self):
        with pytest.raises(ToolError):
            _validate_test_code("MRI'; DROP TABLE providers; --")


def test_allowed_rank_metrics_are_real_columns():
    # every allowlisted metric must be an actual column on ProviderTestMonthMetric,
    # so rank_provider_waits's getattr() never hits an unexpected attribute
    from llm_project.db.nhs_schema import ProviderTestMonthMetric

    for metric in ALLOWED_RANK_METRICS:
        assert hasattr(ProviderTestMonthMetric, metric), f"{metric} is not a real column"
