"""Canonical NHS diagnostics schema (plan.md Step 2): dimensions, facts, and
derived tables for provider-level diagnostic waiting-time and activity data.

Grounded in the real DM01/CDC files inspected during Step 1 (see
DATA_SOURCES.md and docs/data_dictionary.md) — not a guess at the source
schema. Shares `Base`/engine with db/models.py (the app interaction log) so
`init_db()` creates both in one call.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from llm_project.db.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Dimensions ---------------------------------------------------------


class Provider(Base):
    __tablename__ = "providers"

    provider_code: Mapped[str] = mapped_column(String, primary_key=True)
    provider_name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"

    test_code: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "MRI"
    test_name: Mapped[str] = mapped_column(String)
    cdc_alias: Mapped[str] = mapped_column(String, nullable=True)  # CDC file's full name, e.g. "Magnetic Resonance Imaging"


class ReportingPeriod(Base):
    __tablename__ = "reporting_periods"

    period_id: Mapped[str] = mapped_column(String, primary_key=True)  # ISO "YYYY-MM"
    period_month: Mapped[date] = mapped_column(Date)
    period_label: Mapped[str] = mapped_column(String)  # source label, e.g. "DM01-MAY-2026"
    is_complete: Mapped[bool] = mapped_column(Boolean, default=True)


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset: Mapped[str] = mapped_column(String)  # "dm01" | "cdc"
    url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    reporting_period_id: Mapped[str] = mapped_column(
        ForeignKey("reporting_periods.period_id"), nullable=True
    )
    revision_label: Mapped[str] = mapped_column(String, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("dataset", "sha256", name="uq_source_files_dataset_hash"),)


# --- Facts ----------------------------------------------------------------
# Grain: one row per (provider, test, reporting period), already aggregated
# across DM01's commissioner breakdown (see docs/data_dictionary.md).


class DiagnosticWaitingFact(Base):
    __tablename__ = "diagnostic_waiting_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_code: Mapped[str] = mapped_column(ForeignKey("providers.provider_code"))
    test_code: Mapped[str] = mapped_column(ForeignKey("diagnostic_tests.test_code"))
    period_id: Mapped[str] = mapped_column(ForeignKey("reporting_periods.period_id"))

    week_00_01: Mapped[int] = mapped_column(Integer)
    week_01_02: Mapped[int] = mapped_column(Integer)
    week_02_03: Mapped[int] = mapped_column(Integer)
    week_03_04: Mapped[int] = mapped_column(Integer)
    week_04_05: Mapped[int] = mapped_column(Integer)
    week_05_06: Mapped[int] = mapped_column(Integer)
    week_06_07: Mapped[int] = mapped_column(Integer)
    week_07_08: Mapped[int] = mapped_column(Integer)
    week_08_09: Mapped[int] = mapped_column(Integer)
    week_09_10: Mapped[int] = mapped_column(Integer)
    week_10_11: Mapped[int] = mapped_column(Integer)
    week_11_12: Mapped[int] = mapped_column(Integer)
    week_12_13: Mapped[int] = mapped_column(Integer)
    week_13_plus: Mapped[int] = mapped_column(Integer)
    total_waiting: Mapped[int] = mapped_column(Integer)  # verified == sum(weeks) at load time

    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"))
    source_row_count: Mapped[int] = mapped_column(Integer)  # raw commissioner-level rows aggregated in
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    transformation_version: Mapped[str] = mapped_column(String, default="v1")

    __table_args__ = (
        UniqueConstraint("provider_code", "test_code", "period_id", name="uq_waiting_fact_grain"),
        CheckConstraint("total_waiting >= 0", name="ck_waiting_total_nonneg"),
    )


class DiagnosticActivityFact(Base):
    __tablename__ = "diagnostic_activity_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_code: Mapped[str] = mapped_column(ForeignKey("providers.provider_code"))
    test_code: Mapped[str] = mapped_column(ForeignKey("diagnostic_tests.test_code"))
    period_id: Mapped[str] = mapped_column(ForeignKey("reporting_periods.period_id"))

    waiting_list_activity: Mapped[int] = mapped_column(Integer)
    planned_activity: Mapped[int] = mapped_column(Integer)
    unscheduled_activity: Mapped[int] = mapped_column(Integer)
    total_activity: Mapped[int] = mapped_column(Integer)  # verified == sum of the three above

    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"))
    source_row_count: Mapped[int] = mapped_column(Integer)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    transformation_version: Mapped[str] = mapped_column(String, default="v1")

    __table_args__ = (
        UniqueConstraint("provider_code", "test_code", "period_id", name="uq_activity_fact_grain"),
        CheckConstraint("total_activity >= 0", name="ck_activity_total_nonneg"),
    )


class CdcActivityFact(Base):
    """Keyed on CDC code, not provider_code — see DATA_SOURCES.md: there is no
    guaranteed CDC-to-provider mapping in the source file. provider_code stays
    NULL until an explicit mapping is established (never inferred/forced)."""

    __tablename__ = "cdc_activity_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cdc_code: Mapped[str] = mapped_column(String)
    cdc_name: Mapped[str] = mapped_column(String)
    region_code: Mapped[str] = mapped_column(String, nullable=True)
    region_name: Mapped[str] = mapped_column(String, nullable=True)
    icb: Mapped[str] = mapped_column(String, nullable=True)

    test_code: Mapped[str] = mapped_column(ForeignKey("diagnostic_tests.test_code"))
    period_id: Mapped[str] = mapped_column(ForeignKey("reporting_periods.period_id"))
    provider_code: Mapped[str] = mapped_column(ForeignKey("providers.provider_code"), nullable=True)

    activity_count: Mapped[int] = mapped_column(Integer)

    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    transformation_version: Mapped[str] = mapped_column(String, default="v1")

    __table_args__ = (
        UniqueConstraint("cdc_code", "test_code", "period_id", name="uq_cdc_fact_grain"),
        CheckConstraint("activity_count >= 0", name="ck_cdc_activity_nonneg"),
    )


# --- Derived (recomputed by the metrics step, not source-of-truth) --------


class ProviderTestMonthMetric(Base):
    __tablename__ = "provider_test_month_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_code: Mapped[str] = mapped_column(ForeignKey("providers.provider_code"))
    test_code: Mapped[str] = mapped_column(ForeignKey("diagnostic_tests.test_code"))
    period_id: Mapped[str] = mapped_column(ForeignKey("reporting_periods.period_id"))

    total_waiting: Mapped[int] = mapped_column(Integer)
    waiting_6_plus_weeks: Mapped[int] = mapped_column(Integer)
    percentage_waiting_6_plus_weeks: Mapped[float] = mapped_column(Float)
    total_activity: Mapped[int] = mapped_column(Integer)
    cdc_activity: Mapped[int] = mapped_column(Integer, nullable=True)

    waiting_list_monthly_change: Mapped[float] = mapped_column(Float, nullable=True)
    waiting_list_yearly_change: Mapped[float] = mapped_column(Float, nullable=True)
    activity_monthly_change: Mapped[float] = mapped_column(Float, nullable=True)
    activity_yearly_change: Mapped[float] = mapped_column(Float, nullable=True)
    pressure_proxy: Mapped[float] = mapped_column(Float, nullable=True)
    persistent_pressure_months: Mapped[int] = mapped_column(Integer, nullable=True)

    quality_flag: Mapped[str] = mapped_column(String, default="complete")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("provider_code", "test_code", "period_id", name="uq_metrics_grain"),
        CheckConstraint(
            "percentage_waiting_6_plus_weeks >= 0 AND percentage_waiting_6_plus_weeks <= 100",
            name="ck_pct_range",
        ),
    )


class BottleneckScore(Base):
    __tablename__ = "bottleneck_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_code: Mapped[str] = mapped_column(ForeignKey("providers.provider_code"))
    test_code: Mapped[str] = mapped_column(ForeignKey("diagnostic_tests.test_code"))
    period_id: Mapped[str] = mapped_column(ForeignKey("reporting_periods.period_id"))
    weighting_scenario: Mapped[str] = mapped_column(String)  # balanced | waiting_focused | capacity_focused

    score: Mapped[float] = mapped_column(Float)
    component_long_wait: Mapped[float] = mapped_column(Float)
    component_waiting_growth: Mapped[float] = mapped_column(Float)
    component_activity_imbalance: Mapped[float] = mapped_column(Float)
    component_persistence: Mapped[float] = mapped_column(Float)
    component_cdc_indicator: Mapped[float] = mapped_column(Float)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint(
            "provider_code", "test_code", "period_id", "weighting_scenario", name="uq_bottleneck_grain"
        ),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_bottleneck_score_range"),
    )
