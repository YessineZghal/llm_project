# ScanFlow AI

ScanFlow AI is an application for exploring NHS England diagnostic
waiting-time and activity data. It ingests official published data,
computes validated operational metrics, and answers questions about
provider-level diagnostic waiting times through controlled analytical
tools. It is built as a project for the DataTalksClub LLM Zoomcamp course.

This project is under active development. The sections below describe
what is implemented and verified today, and what is planned. A detailed,
continuously updated build log is kept in `agent/PROGRESS.md`; the full
21-step project specification is in `plan.md`.

## Project status

The project follows an eight-milestone build plan. Status as of this
version:

| Milestone | Description | Status |
|---|---|---|
| 1 | Foundation: data discovery, canonical schema | Complete |
| 2 | Reliable ingestion: deterministic, idempotent pipeline, Kestra orchestration | Complete |
| 3 | Analytics vertical slice: derived metrics, analytical tools, minimal interface | Complete |
| 4 | Retrieval-augmented generation: profile generation, retrieval evaluation | Not started |
| 5 | Agent: query rewriting, full tool set, agent evaluation | Not started |
| 6 | Quality and interface: grounded generation, LLM evaluation, full interface | Not started |
| 7 | Operations: monitoring extension, containerization finalization | Partially complete |
| 8 | Submission: documentation, rubric audit | Not started |

Everything described as "complete" below has been verified against real
data, not sample or synthetic data, and real infrastructure (a live
Postgres database, a live Kestra orchestration instance).

## Problem statement

NHS England publishes detailed monthly diagnostic waiting-time and
activity data covering every provider in England, across many diagnostic
test types. This data is valuable for understanding where diagnostic
capacity is under pressure, but it is distributed as large, wide CSV
files with provider and commissioner-level granularity that are not
practical to explore directly. ScanFlow AI ingests this data, computes
standard operational metrics from it, and will provide a natural-language
interface for asking questions such as which providers have the highest
long-wait rates for a given test, or how a provider's waiting list has
changed over time.

The application answers operational and informational questions about
aggregate, provider-level data. It does not provide clinical advice,
individual patient prioritization, or any patient-level information, and
this restriction is enforced by design: the data itself is aggregate
counts by provider, test, and month, with no patient-level records
present anywhere in the system.

## Data sources and licence

The primary data source is NHS England's Monthly Diagnostic Waiting
Times and Activity return (known as DM01), supplemented by Community
Diagnostic Centre activity data. Both are published under the Open
Government Licence version 3.0. Full details, including the exact files
used, their formats, and verification notes, are in `DATA_SOURCES.md`.
Column-level documentation of both source files, derived directly from
inspecting the real downloaded files, is in `docs/data_dictionary.md`.

Attribution: this project uses publicly accessible aggregate information
published by NHS England under the Open Government Licence v3.0. The
data was cleaned, normalized, and transformed for an independent
educational project. This project is not endorsed by NHS England.

The current scope covers four diagnostic groups (MRI, CT, non-obstetric
ultrasound, and colonoscopy), matching the mandatory minimum scope
defined in `plan.md`, and a small number of recent reporting months. The
ingestion pipeline is designed to extend to a longer historical window
without code changes; the current month range was chosen deliberately to
keep local development iteration fast, per the project's own
vertical-slice-first principle.

## Architecture

```
NHS England publication pages (DM01, CDC)
        |
        v
Source discovery (scrapes publication pages for current file links)
        |
        v
Download, hash, validate, normalize, aggregate to provider level
        |
        v
PostgreSQL: dimension tables, fact tables, derived tables
        |
        v
Derived metrics and bottleneck score computation
        |
        v
Analytical tools (typed input and output, parameterized SQL only)
        |
        v
Streamlit interface
        |
        v
Interaction logging (PostgreSQL) and monitoring dashboard
```

Ingestion is orchestrated by Kestra, running the same Docker image as the
rest of the application so dependencies never drift between the two.

### Technology choices

| Concern | Choice |
|---|---|
| Orchestration | Kestra |
| Structured data storage | PostgreSQL, via SQLAlchemy |
| Full-text and vector search (planned, Milestone 4) | minsearch and Elasticsearch |
| Interface | Streamlit |
| Monitoring | PostgreSQL interaction log and a Streamlit dashboard |
| Containerization | Docker Compose |
| Language model provider (planned, Milestones 4 to 6) | OpenAI |

A number of deliberate substitutions were made relative to the original
21-step specification in `plan.md`, which called for Prefect, a separate
FastAPI backend, PostgreSQL with the pgvector extension, and Grafana.
These were replaced with Kestra, a Streamlit-only interface, minsearch
and Elasticsearch, and a Streamlit monitoring dashboard, respectively, to
reuse tooling already established for this course rather than
introducing a second stack. The rationale for each substitution, and
what is gained or given up by it, is recorded in `agent/PLAN.md`.

## Data model

The canonical schema separates source-of-truth fact tables from derived,
recomputable tables, and every fact row is traceable to the exact source
file it came from.

Dimension tables: `providers`, `diagnostic_tests`, `reporting_periods`,
`source_files`.

Fact tables: `diagnostic_waiting_facts` (weekly waiting bands and total
waiting list, one row per provider, test, and reporting month, aggregated
from the source file's provider-by-commissioner granularity),
`diagnostic_activity_facts` (waiting-list, planned, and unscheduled
activity), and `cdc_activity_facts` (Community Diagnostic Centre
activity, keyed by CDC rather than by provider, since the source data
does not include a CDC-to-provider mapping).

Derived tables: `provider_test_month_metrics` (long-wait percentage,
month-over-month and year-over-year change, a pressure proxy, and a
persistence count) and `bottleneck_scores` (a composite score under
three weighting scenarios, described below).

Every fact table row carries a foreign key to the exact `source_files`
row it was loaded from, and constraints reject duplicate facts and
invalid percentages. The full schema, generated from the SQLAlchemy
models, is in `database/schema.sql`; the models themselves are in
`src/llm_project/db/nhs_schema.py`.

A genuinely missing value (for example, a month-over-month change with
no prior month loaded, or a Community Diagnostic Centre activity figure
that cannot yet be linked to a provider) is stored as a database null,
never as a fabricated zero.

## Ingestion pipeline

Ingestion is deterministic and idempotent. Given a source file URL, the
pipeline downloads the file, computes its content hash, checks whether a
file with that hash has already been ingested (in which case it is
skipped rather than reprocessed), validates it, aggregates it to
provider level, and loads it into the canonical schema. Running ingestion
twice against the same source produces no duplicate records.

Validation is strict: if a row's reported total waiting list does not
equal the sum of its own weekly waiting bands, or a row's reported total
activity does not equal the sum of its own activity components, the
pipeline raises an error rather than loading the row. Every ingestion run
writes a machine-readable quality report to `data/quality_reports/`.

Source files are not hardcoded. `src/llm_project/ingest/nhs_discover.py`
scrapes NHS England's publication pages for the current month's file
links, so the pipeline picks up new monthly releases automatically
rather than requiring a code change each month.

The pipeline is orchestrated by a Kestra flow,
`flows/ingest_diagnostics.yaml`, scheduled to run daily. It has been
verified running end to end inside a live Kestra instance, not only as a
standalone script.

Relevant modules:

- `src/llm_project/ingest/nhs_source.py`: file download and parsing.
- `src/llm_project/ingest/nhs_pipeline.py`: validation, normalization,
  loading, idempotency, and quality reporting.
- `src/llm_project/ingest/nhs_discover.py`: source file discovery.
- `src/llm_project/ingest/nhs_discovered_run.py`: the discover-then-load
  entry point used by the Kestra flow.

## Derived metrics and the bottleneck score

Numerical results are never produced by a language model. All figures
shown by the application are computed in Python from validated database
facts, in `src/llm_project/analytics/metrics.py`, and stored before any
question is asked. The analytical tools and interface only read
already-computed values.

For every provider, diagnostic test, and reporting month, the pipeline
computes: total waiting list, the count and percentage waiting six weeks
or longer, total activity, month-over-month and year-over-year change in
both waiting list and activity, a pressure proxy (waiting-list growth
minus activity growth), and a persistence count (the number of loaded
prior months in which the pressure proxy was positive).

The bottleneck score is a project-specific composite indicator, not an
official NHS metric, and is presented as such throughout the
application. It combines five normalized components: long-wait
percentage, waiting-list growth, activity imbalance, persistence, and a
Community Diagnostic Centre capacity indicator, weighted 30, 25, 20, 15,
and 10 percent respectively in the balanced scenario. Two additional
scenarios, waiting-focused and capacity-focused, apply different
weights to the same components, so that a provider's relative ranking
can be examined under different assumptions rather than presented as a
single authoritative number. Where a component is genuinely unavailable
for a given provider and period (most currently, the Community
Diagnostic Centre indicator, since no CDC-to-provider mapping exists
yet), it is excluded from that provider's score and the remaining
weights are renormalized, rather than the missing component being
treated as zero.

All of this has been verified against real data. As one example: East
Kent Hospitals University NHS Foundation Trust, MRI, May 2026, computes
to 40.82 percent waiting six weeks or longer, which matches a direct
hand calculation from the underlying fact (5,084 of 12,455 patients
waiting).

## Analytical tools

Two of the nine analytical tools specified in `plan.md` are implemented
so far, in `src/llm_project/analytics/tools.py`. The remaining seven are
planned for Milestone 5, alongside the agent that will route natural-
language questions to them.

`get_provider_profile` returns the full metric profile for one provider,
diagnostic test, and reporting period. `rank_provider_waits` returns the
top or bottom providers for a diagnostic test and reporting period,
ordered by one of a fixed set of allowed metrics.

Both tools share the same design: inputs are validated Pydantic models,
diagnostic test codes and rankable metrics are restricted to an
allowlist rather than accepting arbitrary values, all data access is
parameterized SQL through SQLAlchemy with no arbitrary query
construction, and every response includes the exact reporting period it
covers, a citation of where the figures come from, any relevant
data-quality warnings, and its own execution time.

## Interface

The current Streamlit interface, `src/llm_project/app/streamlit_app.py`,
provides two views built directly on the analytical tools above. It does
not yet use a language model; this is deliberate, matching the project's
principle that numerical answers must come from code, not from a model,
and the natural-language interface arrives once retrieval and the agent
are built in later milestones.

The "Rank providers" view answers questions of the form: which providers
have the highest or lowest value of a given metric, for a given
diagnostic test and reporting period. The "Provider profile" view shows
the full metric profile for one selected provider, test, and period,
including month-over-month change and any data-quality warnings.

Every result in both views displays its exact reporting period and a
citation of its source, and every interaction is logged for monitoring.

To run the interface locally:

```
uv run streamlit run src/llm_project/app/streamlit_app.py
```

## Monitoring

Every interaction with the application is logged to PostgreSQL,
including the question asked, the answer produced, which tool served it,
response time, and any user feedback. This reuses the interaction-log
pattern already established for this project rather than introducing a
separate mechanism.

A monitoring dashboard, `src/llm_project/app/pages/1_Monitoring.py`,
reads this log and presents summary statistics and charts covering
volume over time, response time distribution, and feedback. This
dashboard will be extended in Milestone 7 to the fuller interaction-log
schema and chart set specified in `plan.md`, including tool success
rate, questions by diagnostic test, and ingestion freshness.

## Running the project

### Docker Compose

```
cp .env.example .env
docker compose up --build -d app elasticsearch app_postgres
```

This starts the application, its PostgreSQL database, and Elasticsearch
(used from Milestone 4 onward). Add `kestra kestra_postgres` to the
command, or omit the service list entirely to start everything, to also
run the orchestration layer.

The database schema is created automatically on first use. Data must be
loaded separately; see below.

### Manual setup

```
uv sync
cp .env.example .env
docker compose up -d app_postgres
uv run python -m llm_project.ingest.nhs_pipeline <DM01 zip url> [<DM01 zip url> ...] --cdc <CDC csv url>
uv run python -m llm_project.analytics.metrics
uv run streamlit run src/llm_project/app/streamlit_app.py
```

Current source file URLs can be found by running
`uv run python -m llm_project.ingest.nhs_discover`, which prints the
current month's file links directly from NHS England's publication
pages, or found in `DATA_SOURCES.md`.

### Orchestrated ingestion through Kestra

```
docker compose up -d kestra kestra_postgres app_postgres
```

Once Kestra is running, register `flows/ingest_diagnostics.yaml` through
its API or web interface at `localhost:8080`. The flow discovers current
source files and loads them on a daily schedule, and is safe to trigger
manually at any time; already-ingested files are skipped rather than
reprocessed.

## Environment variables

See `.env.example` for the complete, documented list. At minimum, an
`OPENAI_API_KEY` is required for functionality planned in later
milestones; the current milestone's functionality requires only a
running PostgreSQL instance.

## Testing

```
uv run pytest tests/unit/ -v
```

Unit tests cover source file parsing, validation rejection behavior,
provider-level aggregation, reporting-period label parsing, and fiscal-
year boundary logic, using small deterministic fixtures rather than live
network access.

## Project structure

```
src/llm_project/
  config.py              environment variables, paths, model and index names
  ingest/
    nhs_source.py          DM01 and CDC file parsing and validation
    nhs_pipeline.py         download, normalize, load, idempotency, quality reports
    nhs_discover.py          source file discovery from NHS publication pages
    nhs_discovered_run.py     discover-then-load entry point for Kestra
  db/
    nhs_schema.py           canonical schema: dimensions, facts, derived tables
    models.py                 interaction log (conversations, feedback)
    client.py                  logging and dashboard query helpers
  analytics/
    metrics.py               derived metrics and bottleneck score computation
    tools.py                   analytical tools (get_provider_profile, rank_provider_waits)
  app/
    streamlit_app.py         interface
    pages/1_Monitoring.py      monitoring dashboard
  search/                   retrieval layer, in place ahead of Milestone 4
  eval/                     evaluation scripts, in place ahead of Milestone 4
  rag/                      retrieval-augmented generation pipeline, in place ahead of Milestone 4
flows/ingest_diagnostics.yaml   Kestra orchestration flow
database/schema.sql              generated schema reference
docs/data_dictionary.md          source file column documentation
tests/unit/                      unit tests
DATA_SOURCES.md                  data source registry
plan.md                          original 21-step project specification
agent/PLAN.md                    approved implementation plan and rationale
agent/PROGRESS.md                continuously updated build log
```

## Known limitations

The current reporting-month window is short (a small number of recent
months), which limits year-over-year comparison and the persistence
metric to what is actually loaded; both are reported as unavailable
rather than approximated when insufficient history exists. Community
Diagnostic Centre activity cannot currently be linked to a specific
provider, since the source data does not include that mapping; it is
tracked and retrievable by centre, region, and integrated care board,
and this limitation is stated directly wherever it is relevant, rather
than silently omitted. The bottleneck score is a project-specific
indicator for relative comparison, not an official or clinically
validated measure, and is labeled as such throughout. The interface does
not yet accept natural-language questions; this arrives with retrieval
and the agent in later milestones.

## Roadmap

Milestone 4 will generate a retrieval corpus from the loaded data
(provider profiles, diagnostic test explanations, metric definitions,
and methodology notes), index it using the retrieval layer already in
place, and evaluate multiple retrieval approaches against a ground-truth
question set. Milestone 5 will add query rewriting and intent
classification, the remaining seven analytical tools, and an agent that
routes between retrieval and tools, evaluated against a labeled test
set. Milestone 6 will add grounded, cited answer generation, evaluate
multiple end-to-end pipeline configurations, and complete the interface
with the additional views specified in `plan.md`. Milestone 7 will
extend monitoring to the full specified chart set. Milestone 8 covers
final documentation and a rubric audit.

## Course rubric mapping

| Criterion | Current status |
|---|---|
| Problem description | Described above |
| Knowledge base and language model | Planned for Milestone 4 |
| Retrieval evaluation | Planned for Milestone 4 |
| Language model evaluation | Planned for Milestone 6 |
| Interface | Streamlit, functional for the tools implemented so far |
| Ingestion pipeline | Automated, orchestrated by Kestra, verified end to end |
| Monitoring | Interaction logging implemented; dashboard implemented, to be extended |
| Containerization | Docker Compose covers the application, database, search, and orchestration services |
| Reproducibility | Pinned dependencies, documented environment variables, verified setup instructions above |
