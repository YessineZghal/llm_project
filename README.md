# ScanFlow AI

ScanFlow AI is an application for exploring NHS England diagnostic
waiting-time and activity data. It ingests official published data,
computes validated operational metrics, retrieves explanatory content from
a generated knowledge base, and answers questions about provider-level
diagnostic waiting times through an agent that routes between controlled
analytical tools and retrieval. It is built as a project for the
DataTalksClub LLM Zoomcamp course.

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
| 4 | Retrieval-augmented generation: corpus generation, retrieval evaluation | Complete |
| 5 | Agent: query rewriting, full tool set, agent, agent evaluation | Complete |
| 6 | Quality and interface: grounded generation, LLM evaluation, full interface | Partially complete |
| 7 | Operations: monitoring extension, containerization finalization | Partially complete |
| 8 | Submission: documentation, rubric audit | Not started |

Everything described as "complete" below has been verified against real
data and a real running system - a live Postgres database, a live
Elasticsearch index, a live Kestra orchestration instance, and a real
agent making real OpenAI calls, not mocked.

## Problem statement

NHS England publishes detailed monthly diagnostic waiting-time and
activity data covering every provider in England, across many diagnostic
test types. This data is valuable for understanding where diagnostic
capacity is under pressure, but it is distributed as large, wide CSV
files with provider and commissioner-level granularity that are not
practical to explore directly. ScanFlow AI ingests this data, computes
standard operational metrics from it, and answers natural-language
questions such as which providers have the highest long-wait rates for a
given test, how a provider's waiting list has changed over time, or what
a given metric or diagnostic test means.

The application answers operational and informational questions about
aggregate, provider-level data. It does not provide clinical advice,
individual patient prioritization, or any patient-level information, and
this restriction is enforced both by design (the data itself is aggregate
counts by provider, test, and month, with no patient-level records
present anywhere in the system) and by the agent's own rules, which
explicitly refuse individual clinical requests.

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
RAG corpus generation (provider profiles, definitions, methodology)
        |
        v
Elasticsearch / minsearch indexing
        |
        v
        User question
        |
        v
Intent classification + entity resolution  ---->  Analytical tools
        |                                         (typed, parameterized SQL only)
        v                                                |
Agent (tool-calling, routes between the two)  <-----------
        |
        v
Grounded, cited answer
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
| Full-text and vector search | minsearch (text and vector) and Elasticsearch (text, kNN, hybrid, hybrid with reranking) - 6 approaches |
| Reranking | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Agent tool-calling | toyaikit |
| Language model | OpenAI (gpt-4o-mini by default) |
| Interface | Streamlit |
| Monitoring | PostgreSQL interaction log and a Streamlit dashboard |
| Containerization | Docker Compose |

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
models, is in `database/schema.sql`; a full entity-relationship diagram
is in `docs/architecture.md`; the models themselves are in
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
question is asked. The analytical tools, agent, and interface only read
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
for a given provider and period, it is excluded from that provider's
score and the remaining weights are renormalized, rather than the
missing component being treated as zero.

All of this has been verified against real data. As one example: East
Kent Hospitals University NHS Foundation Trust, MRI, May 2026, computes
to 40.82 percent waiting six weeks or longer, which matches a direct
hand calculation from the underlying fact (5,084 of 12,455 patients
waiting). Formula-level unit tests with hand-calculated examples are in
`tests/unit/test_metrics.py`.

## Retrieval-augmented generation

`src/llm_project/rag/generate_corpus.py` generates the knowledge base
entirely from validated database facts and static reference text, making
no language-model calls itself. It produces 1,870 documents: one
provider-test profile per real (provider, diagnostic test) combination
with loaded data (1,856 of them), 4 diagnostic-test definitions, 6 metric
definitions, and 4 methodology and data-quality documents. Every number
in a provider profile traces directly to a row in
`provider_test_month_metrics`.

This corpus is indexed using the project's retrieval layer
(`src/llm_project/search/`) unchanged - the same six retrieval
approaches (minsearch text and vector, Elasticsearch text/kNN/hybrid, and
hybrid with cross-encoder reranking) built and evaluated for an earlier
phase of this project work against a different corpus, simply repointed
at the new one.

Retrieval was re-evaluated against the new corpus following plan.md Step
8: a ground-truth set of 120 questions, stratified across provider
profiles, test definitions, metric definitions, methodology, comparison-
support questions, and 15 hand-curated genuinely unanswerable questions
(`src/llm_project/eval/generate_ground_truth.py`,
`data/eval/retrieval_ground_truth.jsonl`). Evaluation
(`src/llm_project/eval/evaluate_retrieval.py`) computes Hit Rate@5, MRR,
Recall@5, Recall@10, and NDCG@5 for every method:

| method | hit_rate@5 | MRR | Recall@5 | Recall@10 | NDCG@5 |
|---|---|---|---|---|---|
| **es_hybrid_rerank** | **0.981** | **0.948** | **0.981** | **0.981** | **0.956** |
| es_hybrid | 0.952 | 0.866 | 0.952 | 0.981 | 0.888 |
| minsearch_vector | 0.886 | 0.814 | 0.886 | 0.924 | 0.832 |
| es_text | 0.790 | 0.581 | 0.790 | 0.943 | 0.634 |
| minsearch_text | 0.781 | 0.716 | 0.781 | 0.819 | 0.732 |
| es_knn | 0.743 | 0.696 | 0.743 | 0.752 | 0.707 |

`es_hybrid_rerank` wins clearly and is the default in
`src/llm_project/search/retriever.py` (unchanged from before this
re-evaluation - the winner held). Of 105 answerable questions, only 2
were missed, both genuinely ambiguous (for example, asking about "the"
ultrasound waiting list at a provider name shared by several similarly-
named facilities without enough detail to disambiguate) rather than
retrieval defects. Full results: `data/eval/retrieval_eval_results.csv`;
error analysis: `data/eval/retrieval_error_analysis.md`. Every method
returns *some* result even for the deliberately unanswerable questions
(similarity search has no built-in abstention) - recognizing "no good
answer exists" is the agent's job via grounding and refusal behavior, not
retrieval's.

## Analytical tools

All nine analytical tools specified in `plan.md` are implemented, in
`src/llm_project/analytics/tools.py`: `get_provider_profile`,
`rank_provider_waits`, `compare_provider_waits`, `analyze_waiting_trend`,
`compare_activity_and_waiting`, `analyze_cdc_activity`,
`find_similar_providers`, `simulate_capacity_change`, and
`retrieve_metric_definition` (the only one that calls the retrieval layer
rather than SQL directly, since metric definitions are reference text,
not a computed fact). A tenth tool, `get_bottleneck_ranking`, was added to
make the bottleneck score (computed by every metrics run, but not covered
by `rank_provider_waits`'s allowlist, since it lives in its own table)
actually queryable - by test, period, and weighting scenario.

Every tool shares the same design: inputs are validated Pydantic models,
diagnostic test codes and rankable metrics are restricted to an
allowlist rather than accepting arbitrary values, all data access is
parameterized SQL through SQLAlchemy with no arbitrary query
construction, and every response includes the exact reporting period it
covers, a citation of where the figures come from, any relevant
data-quality warnings, and its own execution time.

`simulate_capacity_change` is explicitly a simplified, illustrative
projection (assuming constant demand), never a forecast, and its result
always carries a warning saying so - matching plan.md's requirement for
the Capacity Scenario page.

## Query rewriting, intent classification, and the agent

`src/llm_project/rag/intent.py` implements plan.md Step 10: a language
model classifies a question into one of nine intents and extracts
mentioned entities (provider names, diagnostic test, metric, dates), but
resolving those mentions against real data is done in code, not trusted
from the model - `resolve_provider` looks up real providers and
surfaces every match visibly when a name is ambiguous (for example,
"Spire" resolves to 10 real candidate hospitals, not a guessed one)
rather than silently picking one; `resolve_test` and `resolve_metric`
reject anything outside the fixed allowlists rather than guessing.

`src/llm_project/rag/agent.py` is a toyaikit tool-calling agent wired to
all nine analytical tools plus knowledge-base search, following rules
enforced in its system prompt: never calculate a number itself (every
figure must come from a tool), always state the exact reporting period,
always relay a tool's data-quality warnings, never use causal language,
and refuse individual clinical requests (predicting a personal wait time,
prioritizing a specific patient, diagnosis, or treatment advice).

Verified with real questions and real OpenAI calls: a ranking question
correctly calls `rank_provider_waits` and returns the exact figures
independently verified in the analytical-tools section above; an
individual-medical question is correctly refused; a definition question
is correctly answered via knowledge-base retrieval; a trend question
about a real provider produces a nuanced description of a genuinely
non-monotonic real data series rather than an oversimplified one-word
summary.

### Agent evaluation

`src/llm_project/eval/evaluate_agent.py` implements plan.md Step 12: a
test bank of 117 cases (exceeding the "at least 100" requirement) covering
every intent, all nine tools, and plan.md's named difficult cases -
partial and ambiguous provider names, missing parameters, and 15
unsupported-medical-request safety cases - run against the real intent
classifier and the real agent, not mocked. It measures intent accuracy,
tool-selection accuracy, provider- and test-code-extraction accuracy, and
refusal correctness separately. Results:
`data/eval/agent_eval_results.csv`; error analysis:
`data/eval/agent_error_analysis.md`.

**Real measured results:**

| Measure | Accuracy |
|---|---|
| Intent accuracy | 92.3% (108/117) |
| Tool-selection accuracy | 83.8% (98/117) |
| Provider-code extraction (of 44 applicable cases) | 100% |
| Test-code extraction (of 67 applicable cases) | 100% |
| Refusal correctness (15 unsupported-medical-request cases) | 100% |

The raw tool-selection number understates real quality once the actual
misses are read (`data/eval/agent_error_analysis.md`). Manually
categorizing all 19 tool-selection "misses": roughly a quarter are cases
where the agent did the *right* thing and the test label was wrong - for
example, "Tell me about SPAMEDICA's CT waiting list" expected a direct
`get_provider_profile` call, but SpaMedica has multiple branches, so the
agent correctly called `resolve_provider_code`, got an ambiguous result,
and stopped to ask which branch was meant, exactly as its system prompt
instructs (compare this against otherwise-identical cases using an
unambiguous partial name, like "MEDEFER" or "KINGSNORTH", which chained
correctly into `get_provider_profile` every time). Several more are the
agent choosing a defensible alternative tool - `search_knowledge_base`
(general retrieval) instead of the more specific `retrieve_metric_definition`
for definition questions, which likely still retrieves the right document
since both search the same corpus. A few (3 cases with a missing
diagnostic-test parameter) show the agent proactively calling
`get_provider_profile` once per supported test rather than asking for
clarification - a different but reasonably helpful strategy, not the
behavior the test case assumed. The genuine gap worth tracking: on 4 of 8
methodology questions, the agent answered without calling
`search_knowledge_base` at all. Two of those four ("Is the bottleneck
score an official NHS measure?", "Does this application make causal
claims?") are directly answerable from rules already stated in the
agent's own system prompt, so answering without a tool call is
defensible. The other two ("Where does this data come from?", "Can
figures be revised after publication?") are not covered by the system
prompt and require the methodology documents specifically - these are a
real inconsistency in the "always retrieve for methodology questions"
rule the prompt asks for, worth tightening in Milestone 6.

An earlier version of this evaluation script had its own bug: it counted
all 18 cases with `expected_tool=None` as "safety" cases, when 3 of those
were actually the unrelated "missing diagnostic test parameter" difficult
cases, silently understating refusal correctness. Fixed in
`evaluate_agent.py` (`note == "safety"` instead of `expected_tool is
None`) and reflected in the number above: **100% (15/15)** of the actual
unsupported-medical-request cases were correctly refused, not 83.3%.

## Interface

The Streamlit interface covers all six pages specified in plan.md Step 15.
`src/llm_project/app/streamlit_app.py` has three views: **Ask ScanFlow** is
a chat interface backed by the agent - ask a question in your own words.
**Rank providers** and **Provider profile** call the analytical tools
directly with no language model in the loop, for a structured lookup
rather than a conversation. Four further pages under
`src/llm_project/app/pages/` add dedicated, chart-based views:
**Diagnostic Explorer** (waiting-list, activity, and long-wait trend
charts for one provider and test across every loaded month),
**Provider Comparison** (2 to 5 providers compared on the same test and
period), **Bottleneck Ranking** (ranked score plus a component-level
breakdown chart, so the score is explainable rather than a single opaque
number), and **Capacity Scenario** (a projection chart for the
`simulate_capacity_change` tool, with the simplified-model warning shown
prominently). All charts use a fixed categorical palette and single-hue
magnitude encoding, consistent across every page, and avoid dual-axis
charts throughout (different units get separate charts, never one chart
with two y-axes). Every page logs interactions and/or displays each
result's exact reporting period and source citation.

To run the interface locally:

```
uv run streamlit run src/llm_project/app/streamlit_app.py
```

## Monitoring

Every interaction with the application - from any of the three interface
views - is logged to PostgreSQL: the question, the answer, which mode
served it, response time, cited source documents (extracted from the
agent's own tool calls when it uses knowledge-base search), and any user
feedback.

The monitoring dashboard, `src/llm_project/app/pages/1_Monitoring.py`,
reads this log and presents: interaction volume over time, interactions
by mode, questions by diagnostic test (inferred from question text),
response time distribution, feedback breakdown, and most-cited source
documents - six charts, exceeding the rubric's five-chart threshold for
full monitoring points. It will be extended further in Milestone 7 with
additional charts from plan.md Step 16's list (tool success rate,
ingestion freshness).

## Running the project

### Docker Compose

```
cp .env.example .env
docker compose up --build -d app elasticsearch app_postgres
```

This starts the application, its PostgreSQL database, and Elasticsearch.
Add `kestra kestra_postgres` to the command, or omit the service list
entirely to start everything, to also run the orchestration layer.

The database schema is created automatically on first use. Data and the
search index must be built once; see below.

### Manual setup

```
uv sync
cp .env.example .env
docker compose up -d app_postgres elasticsearch
uv run python -m llm_project.ingest.nhs_pipeline <DM01 zip url> [<DM01 zip url> ...] --cdc <CDC csv url>
uv run python -m llm_project.analytics.metrics
uv run python -m llm_project.rag.generate_corpus
uv run python -m llm_project.search.es_index --recreate
uv run streamlit run src/llm_project/app/streamlit_app.py
```

Current source file URLs can be found by running
`uv run python -m llm_project.ingest.nhs_discover`, which prints the
current month's file links directly from NHS England's publication
pages, or found in `DATA_SOURCES.md`. The `Makefile` wraps these steps
(`make ingest`, `make metrics`, `make corpus`, `make index`).

### Orchestrated ingestion through Kestra

```
docker compose up -d kestra kestra_postgres app_postgres
```

Once Kestra is running, register `flows/ingest_diagnostics.yaml` through
its API or web interface at `localhost:8080`. The flow discovers current
source files and loads them on a daily schedule, and is safe to trigger
manually at any time; already-ingested files are skipped rather than
reprocessed. Note: refreshing the data this way does not automatically
regenerate the RAG corpus or search index - rerun `make corpus index`
afterward.

## Environment variables

See `.env.example` for the complete, documented list. At minimum, an
`OPENAI_API_KEY` is required (used for intent classification, the agent,
and query rewriting), and a running PostgreSQL plus Elasticsearch
instance.

## Security

Every LLM-controlled tool argument passes through a validated Pydantic
model before it is used (see "Analytical tools" above); no user- or
LLM-influenced string is ever interpolated into a SQL or Elasticsearch
query. The two places that use `getattr()` for dynamic column access
(`rank_provider_waits`, `analyze_waiting_trend`) check the requested name
against a fixed allowlist first. Elasticsearch queries use structured
`multi_match`/`knn` bodies, never `query_string` or scripted queries, so
user text cannot be interpreted as query syntax. The Streamlit app never
sets `unsafe_allow_html`, so LLM-generated answer text is always rendered
through Streamlit's sanitized markdown renderer, not raw HTML.

`docker-compose.yml`'s `elasticsearch` and `app_postgres` services are
bound to `127.0.0.1` only (not all network interfaces) - Elasticsearch
runs with security disabled and Postgres ships with an example password
in `.env.example`, both fine for local development but never intended to
be reachable from outside the host. `APP_POSTGRES_PASSWORD` has no
built-in default in `docker-compose.yml`; it must be set in `.env` or the
stack refuses to start. `.env` is gitignored and confirmed never
committed to git history.

## Testing

```
uv run pytest tests/unit/ -v          # no external services required
uv run pytest tests/integration/ -v   # requires app_postgres with data loaded
make test                             # both
```

Unit tests (`tests/unit/`) cover source file parsing, validation
rejection behavior, provider-level aggregation, reporting-period label
parsing, fiscal-year boundary logic, derived-metric formulas with
hand-calculated examples, and analytical-tool input validation - 42
tests, all using small deterministic fixtures with no live network or
database access. Integration tests (`tests/integration/`) verify the
analytical tools and stored metrics against the real loaded database.

`uv run ruff check src tests` is clean; CI (`.github/workflows/ci.yml`)
runs lint, both test suites (integration against a temporary Postgres
service container), a Docker build, and a secret scan on every push.

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
    tools.py                   all 9 analytical tools
  rag/
    generate_corpus.py       RAG corpus generation from database facts
    intent.py                  query rewriting / intent classification / entity resolution
    agent.py                    the tool-calling agent
    pipeline.py, prompts.py, query_rewrite.py   supporting RAG pipeline pieces
  search/                   retrieval layer (6 methods) - reused unchanged
  eval/
    generate_ground_truth.py   retrieval ground truth generation
    evaluate_retrieval.py        retrieval evaluation (6 methods x 5 metrics)
    evaluate_agent.py              agent evaluation (117 cases)
  app/
    streamlit_app.py         interface: Ask ScanFlow, Rank providers, Provider profile
    pages/1_Monitoring.py      monitoring dashboard
flows/ingest_diagnostics.yaml   Kestra orchestration flow
database/schema.sql              generated schema reference
docs/architecture.md             system diagram, full ERD, design principles
docs/data_dictionary.md          source file column documentation
docs/rubric-checklist.md         course rubric tracked against status
tests/unit/, tests/integration/  test suites
Makefile                         up/ingest/metrics/corpus/index/test/evaluate/app targets
.github/workflows/ci.yml         lint, tests, Docker build, secret scan
DATA_SOURCES.md                  data source registry
plan.md                          original 21-step project specification
agent/PLAN.md                    approved implementation plan and rationale
agent/PROGRESS.md                continuously updated build log
```

## Example questions

- Which providers have the highest MRI long-wait rates?
- How has [provider]'s CT waiting list changed over the loaded months?
- Compare [provider A] and [provider B] for non-obstetric ultrasound.
- Did activity grow faster than the waiting list at [provider] for colonoscopy?
- What is the Community Diagnostic Centre activity in London?
- What would 200 extra MRI procedures per month do to [provider]'s waiting list?
- What does waiting six weeks or longer mean?
- Should I get an MRI sooner than the person ahead of me? (expected: declined - individual clinical request)

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
validated measure, and is labeled as such throughout. Retrieval ground
truth is LLM-generated rather than human-labeled. The monitoring
dashboard's diagnostic-test breakdown is inferred from question text
rather than a dedicated logged field. The retrieval layer's `retrieve()`
interface does not yet accept metadata filters (by provider, test,
document type, or period), which plan.md Step 7 specifies; retrieval
currently relies on the query text alone. Query rewriting extracts dates
as free text but has no dedicated relative-date resolution utility (for
example, "last month" is not parsed - only an explicit `YYYY-MM` or
omitting the period for "latest").

## Roadmap

The remainder of Milestone 6 (a dedicated evidence-package/citation
formatter as its own testable module, and a formal three-way comparison
of answer-generation pipelines per plan.md Step 14 - the agent has been
evaluated as a single configuration, not compared against simpler
alternatives) and Milestone 7 (further monitoring chart extensions: tool
success rate, ingestion freshness, token cost) are the main remaining
work, followed by Milestone 8's final documentation and rubric audit. All
six Streamlit pages from Step 15 are now built.

## Course rubric mapping

| Criterion | Current status |
|---|---|
| Problem description | Described above |
| Knowledge base and language model | Both used: 1,870-document generated corpus, OpenAI-backed agent |
| Retrieval evaluation | 6 methods evaluated, best one (es_hybrid_rerank) used - results above |
| Language model evaluation | Agent evaluated (117 cases); formal multi-pipeline answer comparison planned for Milestone 6 |
| Interface | Streamlit, 7 pages including a full chat interface and 4 chart-based analysis pages |
| Ingestion pipeline | Automated, orchestrated by Kestra, verified end to end |
| Monitoring | Feedback collected and a 6-chart dashboard, exceeding the 5-chart threshold |
| Containerization | Docker Compose covers the application, database, search, and orchestration services |
| Reproducibility | Pinned dependencies, documented environment variables, verified setup instructions above, CI |
