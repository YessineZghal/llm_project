# Architecture

## System flow

```
NHS England publication pages (DM01, CDC)
        |
        v
Source discovery (src/llm_project/ingest/nhs_discover.py)
        |
        v
Download, hash, validate, normalize, aggregate to provider level
(src/llm_project/ingest/nhs_source.py, nhs_pipeline.py)
        |
        v
PostgreSQL: dimension and fact tables (src/llm_project/db/nhs_schema.py)
        |
        v
Derived metrics and bottleneck score (src/llm_project/analytics/metrics.py)
        |
        v
Analytical tools: typed, validated, parameterized SQL only
(src/llm_project/analytics/tools.py)
        |
        v
Streamlit interface (src/llm_project/app/streamlit_app.py)
        |
        v
Interaction log (PostgreSQL) and monitoring dashboard
(src/llm_project/db/client.py, src/llm_project/app/pages/1_Monitoring.py)
```

Ingestion is orchestrated by Kestra (`flows/ingest_diagnostics.yaml`),
running the same Docker image as the rest of the application.

## Entity relationship diagram

Dimension tables are shared reference data. Fact tables hold one row per
provider, diagnostic test, and reporting month (aggregated from the source
file's finer provider-by-commissioner grain), each traceable to the exact
source file it was loaded from. Derived tables are fully recomputable from
the fact tables and are cleared and rewritten on every metrics run, never
hand-edited.

```
providers                    diagnostic_tests             reporting_periods
  provider_code (PK)           test_code (PK)                period_id (PK)
  provider_name                 test_name                     period_month
                                  cdc_alias                     period_label
                                                                  is_complete

source_files
  id (PK)
  dataset (dm01 | cdc)
  url, sha256
  downloaded_at
  reporting_period_id (FK -> reporting_periods, nullable)
  revision_label, row_count

diagnostic_waiting_facts                    diagnostic_activity_facts
  id (PK)                                     id (PK)
  provider_code (FK -> providers)             provider_code (FK -> providers)
  test_code (FK -> diagnostic_tests)          test_code (FK -> diagnostic_tests)
  period_id (FK -> reporting_periods)         period_id (FK -> reporting_periods)
  week_00_01 .. week_13_plus (14 bands)       waiting_list_activity
  total_waiting                               planned_activity
  source_file_id (FK -> source_files)         unscheduled_activity
  source_row_count                            total_activity
  UNIQUE(provider_code, test_code, period_id) source_file_id (FK -> source_files)
                                               source_row_count
                                               UNIQUE(provider_code, test_code, period_id)

cdc_activity_facts
  id (PK)
  cdc_code, cdc_name, region_code, region_name, icb
  test_code (FK -> diagnostic_tests)
  period_id (FK -> reporting_periods)
  provider_code (FK -> providers, nullable - no CDC-to-provider mapping yet)
  activity_count
  source_file_id (FK -> source_files)
  UNIQUE(cdc_code, test_code, period_id)

provider_test_month_metrics (derived, recomputed)      bottleneck_scores (derived, recomputed)
  id (PK)                                                 id (PK)
  provider_code, test_code, period_id                     provider_code, test_code, period_id
  total_waiting, waiting_6_plus_weeks                     weighting_scenario
  percentage_waiting_6_plus_weeks                         score
  total_activity, cdc_activity (nullable)                 component_long_wait
  waiting_list_monthly_change (nullable)                  component_waiting_growth (nullable)
  waiting_list_yearly_change (nullable)                   component_activity_imbalance (nullable)
  activity_monthly_change (nullable)                      component_persistence (nullable)
  activity_yearly_change (nullable)                       component_cdc_indicator (nullable)
  pressure_proxy (nullable)                                UNIQUE(provider_code, test_code,
  persistent_pressure_months                                       period_id, weighting_scenario)
  quality_flag
  UNIQUE(provider_code, test_code, period_id)
```

The full generated DDL is in `database/schema.sql`.

## Design principles reflected in the schema

Every fact is traceable to a source file (`source_file_id` is a required
foreign key on every fact table). A genuinely unknown value is stored as
a database null, never a fabricated zero or an average filled in on its
behalf - this applies to month-over-month change with no prior month
loaded, and to the Community Diagnostic Centre indicator wherever no
provider mapping exists. Derived tables are never a source of truth: they
are deleted and rewritten in full on every run of
`src/llm_project/analytics/metrics.py`, so there is never a risk of a
derived row surviving stale after its underlying facts change.

## Technology substitutions

The original 21-step project specification (`plan.md`) called for
Prefect, a separate FastAPI backend, PostgreSQL with the pgvector
extension, and Grafana. This implementation instead uses Kestra,
Streamlit only, minsearch and Elasticsearch, and a Streamlit monitoring
dashboard respectively, so the project reuses tooling already
established for this course rather than introducing a second stack. Full
rationale for each substitution is recorded in `agent/PLAN.md`.
