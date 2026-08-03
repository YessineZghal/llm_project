# ScanFlow AI — End-to-End Project Execution Plan

> **Project:** Diagnostic Waiting-Time and Capacity Bottleneck Assistant  
> **Project type:** Combined RAG + analytical agent application  
> **Primary domain:** Healthcare operations and diagnostic access  
> **Primary data owner:** NHS England  
> **Target result:** A reproducible, evaluated, monitored, containerized application that directly addresses every project criterion.

---

## 1. Executive decision

Build **ScanFlow AI**, an application that uses public NHS England diagnostic waiting-time and activity data to answer questions such as:

- Which providers have the highest MRI long-wait rates?
- Which diagnostic services have persistent pressure?
- Did diagnostic activity grow faster or slower than the waiting list?
- How do two providers compare over the same period?
- Which Community Diagnostic Centre activities are associated with improving waits?
- What would happen in a simplified scenario if monthly diagnostic activity increased?
- What does a metric such as “waiting six weeks or longer” mean?

The application must use two complementary mechanisms:

1. **Analytical agent tools** for exact calculations, filtering, ranking, comparison, and scenario analysis.
2. **RAG retrieval** for methodology, metric definitions, data limitations, diagnostic-test explanations, and generated provider profiles.

Do not embed every CSV row and expect the LLM to calculate from retrieved text. Numerical facts must come from validated SQL or Python functions.

---

## 2. Important reality: “zero failure” means controlled failure prevention

No software project can be guaranteed to have zero failures. This plan reduces failure risk by using **stage gates**. Do not move to the next phase until the current phase passes its acceptance checks.

Every phase has:

- **Actions:** exact work to perform.
- **Deliverables:** files or features that must exist.
- **Acceptance gate:** objective pass/fail conditions.
- **Failure controls:** checks that prevent hidden problems.

The most important rule is:

> Build and validate a small complete vertical slice before adding more datasets or advanced features.

---

## 3. Final scope

### 3.1 Mandatory MVP scope

Use:

- Monthly Diagnostic Waiting Times and Activity.
- Community Diagnostic Centre activity.
- Official diagnostic methodology and definitions.
- Four diagnostic groups:
  - MRI.
  - CT.
  - Non-obstetric ultrasound.
  - Colonoscopy.
- The latest 24–36 complete reporting months available when ingestion runs.
- Provider-level data.

Implement:

- Automated ingestion.
- PostgreSQL structured storage.
- pgvector knowledge base.
- Full-text and vector retrieval.
- Hybrid search evaluation.
- Document reranking.
- Query rewriting.
- Controlled analytical tools.
- Streamlit interface.
- User feedback.
- Grafana monitoring with at least five charts.
- Complete Docker Compose.
- Retrieval, agent, and LLM evaluation.
- Clear documentation.

### 3.2 Phase-two scope

Add only after the MVP passes all tests:

- Referral to Treatment data.
- More diagnostic groups.
- Provider similarity search.
- Cloud deployment.

### 3.3 Stretch scope

Add only if the full rubric is already satisfied:

- Workforce data.
- Geographic map.
- Advanced capacity simulation.
- Automated monthly data refresh in the deployed environment.
- Multilingual explanations.

### 3.4 Explicitly out of scope

Do not build:

- Individual patient prioritization.
- Clinical advice.
- Diagnosis or treatment recommendations.
- Patient-level predictions.
- Claims that one factor caused another.
- An unrestricted text-to-SQL system.
- An LLM that performs arithmetic without tool validation.

---

## 4. Official source registry

Use publication pages rather than hard-coding one monthly file forever. The ingestion process should discover or configure the latest files.

| Source | Purpose | Official page |
|---|---|---|
| Monthly Diagnostic Waiting Times and Activity | Main waiting and activity data | https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/ |
| Current diagnostic publication year | Monthly CSV extracts and time series | https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/monthly-diagnostics-data-2026-27/ |
| Community Diagnostic Centre activity | Provider-level CDC activity | https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/cdc-management-information/ |
| Referral to Treatment | Optional phase-two data | https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/ |
| Open Government Licence v3.0 | Reuse terms | https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ |

Create `DATA_SOURCES.md` containing:

- Dataset name.
- Official owner.
- Publication page.
- File URL used by each ingestion run.
- Download date.
- File hash.
- Reporting period.
- Revision label.
- Licence.
- Transformations performed.

Use this attribution:

> This project uses publicly accessible aggregate information published by NHS England under the Open Government Licence v3.0. The data was cleaned, normalized, and transformed for an independent educational project. This project is not endorsed by NHS England.

---

## 5. Success definition and rubric mapping

The project is complete only when every row below is demonstrably satisfied.

| Rubric area | Required evidence in the repository |
|---|---|
| Problem description | A clear README section explaining the operational problem, users, value, scope, and limitations. |
| Retrieval flow | A documented knowledge base, retrieval pipeline, prompt construction, LLM call, and citations. |
| Retrieval evaluation | At least three retrieval approaches compared; best measured approach used in production. |
| LLM evaluation | At least two complete answer-generation approaches compared; best measured approach used. |
| Interface | Working Streamlit UI or API with screenshots. |
| Ingestion pipeline | Automated Prefect flow with logs, retries, validation, and repeatable execution. |
| Monitoring | Feedback collection plus dashboard with at least five charts. |
| Containerization | Frontend, backend, database, Prefect, and Grafana started with Docker Compose. |
| Reproducibility | Pinned versions, accessible data, `.env.example`, one-command setup, and verified instructions. |
| Hybrid search | Keyword and vector search combined and evaluated. |
| Reranking | A reranker applied to retrieval candidates and evaluated. |
| Query rewriting | Natural-language questions converted into normalized intent, entities, dates, and metrics. |
| Bonus | Cloud deployment and one or more genuine extra features. |

---

## 6. Proposed system architecture

```text
NHS publication pages and CSV files
              ↓
        Prefect ingestion
              ↓
 download → checksum → schema validation → normalization
              ↓
       PostgreSQL structured tables
              ↓
 derived metrics + provider/test profiles + definitions
              ↓
 PostgreSQL full-text search + pgvector embeddings
              ↓
               User
              ↓
 query rewriting and intent classification
              ↓
     ┌─────────────────────────────┐
     │ Analytical question?        │──→ controlled SQL/Python tool
     │ Explanation question?       │──→ hybrid RAG + reranker
     │ Combined question?          │──→ both branches
     └─────────────────────────────┘
              ↓
      validated evidence package
              ↓
        grounded LLM response
              ↓
 answer + chart/table + citations + limitations
              ↓
   interaction logs + feedback + Grafana
```

---

## 7. Repository structure

Create this structure at the beginning:

```text
scanflow-ai/
├── app/
│   ├── backend/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── schemas.py
│   │   ├── database.py
│   │   ├── agent.py
│   │   ├── query_rewriting.py
│   │   ├── tools.py
│   │   ├── retrieval.py
│   │   ├── reranking.py
│   │   ├── prompting.py
│   │   ├── generation.py
│   │   ├── citations.py
│   │   └── feedback.py
│   └── frontend/
│       ├── streamlit_app.py
│       └── pages/
├── ingestion/
│   ├── flows.py
│   ├── discover_sources.py
│   ├── download.py
│   ├── validate.py
│   ├── normalize.py
│   ├── load_diagnostics.py
│   ├── load_cdc.py
│   ├── build_profiles.py
│   ├── build_embeddings.py
│   └── quality_report.py
├── evaluation/
│   ├── datasets/
│   │   ├── retrieval_ground_truth.jsonl
│   │   ├── agent_test_cases.jsonl
│   │   ├── answer_test_cases.jsonl
│   │   └── safety_test_cases.jsonl
│   ├── evaluate_retrieval.py
│   ├── evaluate_agent.py
│   ├── evaluate_llm.py
│   ├── evaluate_safety.py
│   └── results/
├── monitoring/
│   ├── grafana/
│   └── dashboards/
├── database/
│   ├── migrations/
│   ├── schema.sql
│   └── seed.sql
├── tests/
│   ├── unit/
│   ├── integration/
│   └── end_to_end/
├── scripts/
│   ├── bootstrap.sh
│   ├── run_evaluation.sh
│   └── smoke_test.sh
├── docs/
│   ├── architecture.md
│   ├── data_dictionary.md
│   ├── evaluation.md
│   ├── monitoring.md
│   ├── setup.md
│   └── usage.md
├── screenshots/
├── .github/workflows/ci.yml
├── .env.example
├── .gitignore
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── Makefile
├── requirements.txt
├── DATA_SOURCES.md
├── DATA_LICENSES.md
├── LICENSE
└── README.md
```

---

# Step-by-step execution plan

## Step 0 — Freeze the project contract

### Goal

Prevent uncontrolled scope growth and ambiguous success criteria.

### Actions

- [ ] Create the GitHub repository.
- [ ] Add the project title and one-paragraph problem statement.
- [ ] Add the mandatory scope from Section 3.
- [ ] Add explicit out-of-scope items.
- [ ] Copy the grading rubric into `docs/rubric-checklist.md`.
- [ ] Create one issue for every phase in this plan.
- [ ] Add labels: `data`, `ingestion`, `rag`, `agent`, `evaluation`, `ui`, `monitoring`, `docker`, `docs`, `bug`.
- [ ] Define the default branch and require pull-request checks if working in a team.

### Deliverables

- Repository.
- `README.md` skeleton.
- `docs/rubric-checklist.md`.
- Issue backlog.

### Acceptance gate

A reviewer can read the first page of the README and understand:

- The problem.
- The intended users.
- The data source.
- What the application does.
- What it does not do.

### Failure controls

- Do not add RTT or workforce data yet.
- Do not start frontend work before the data contract is understood.

---

## Step 1 — Perform data discovery before coding ingestion

### Goal

Understand the real files, columns, dimensions, revisions, and quality risks.

### Actions

- [ ] Download three recent monthly diagnostic CSV packages manually.
- [ ] Download the current CDC provider CSV.
- [ ] Save the original files under a local ignored directory such as `data/raw/`.
- [ ] Record file names, sizes, hashes, reporting months, and revision dates.
- [ ] Inspect:
  - Column names.
  - Delimiters and encodings.
  - Provider and commissioner dimensions.
  - Diagnostic test codes and labels.
  - Waiting bands.
  - Activity categories.
  - Null conventions.
  - Suppression markers.
  - Duplicate keys.
- [ ] Identify the minimum columns required for the MVP.
- [ ] Write `docs/data_dictionary.md`.
- [ ] Create a notebook only for exploration; do not make the final application depend on it.

### Deliverables

- `docs/data_dictionary.md`.
- Initial source registry.
- Documented candidate primary key.
- Sample anonymized rows in `tests/fixtures/`.

### Acceptance gate

You can answer all of these without guessing:

- What does one row represent?
- Which field identifies the provider?
- Which field identifies the diagnostic test?
- How are waiting bands represented?
- How is activity represented?
- How are revisions indicated?
- Can a row be uniquely identified?

### Failure controls

- Never invent column names from documentation alone.
- Keep raw files immutable.
- Hash every source file.
- Treat revised files as new source versions.

---

## Step 2 — Define the canonical data model

### Goal

Create a stable internal schema that is independent of monthly source-file changes.

### Actions

- [ ] Create dimension tables:
  - `providers`.
  - `diagnostic_tests`.
  - `reporting_periods`.
  - `source_files`.
- [ ] Create fact tables:
  - `diagnostic_waiting_facts`.
  - `diagnostic_activity_facts`.
  - `cdc_activity_facts`.
- [ ] Create derived tables or materialized views:
  - `provider_test_month_metrics`.
  - `provider_test_trends`.
  - `bottleneck_scores`.
- [ ] Add lineage columns:
  - `source_file_id`.
  - `source_row_number`.
  - `ingested_at`.
  - `transformation_version`.
- [ ] Create database migrations.
- [ ] Add uniqueness, foreign-key, range, and null constraints.

### Minimum derived metric model

```text
provider_code
provider_name
reporting_month
diagnostic_test_code
diagnostic_test_name
total_waiting
waiting_6_plus_weeks
percentage_waiting_6_plus_weeks
total_activity
cdc_activity
waiting_list_monthly_change
waiting_list_yearly_change
activity_monthly_change
activity_yearly_change
pressure_proxy
persistent_pressure_months
bottleneck_score
quality_flag
```

### Deliverables

- `database/schema.sql`.
- Migration files.
- Entity relationship diagram in `docs/architecture.md`.

### Acceptance gate

- The schema loads sample data.
- Duplicate facts are rejected.
- Invalid percentages are rejected.
- Every fact is traceable to a source file.

### Failure controls

- Preserve source values before normalization.
- Do not overwrite historical source versions.
- Use ISO dates and explicit units.

---

## Step 3 — Build a deterministic local ingestion script

### Goal

Prove the transformation logic before introducing workflow orchestration.

### Actions

- [ ] Implement source-file parsing.
- [ ] Normalize column names.
- [ ] Normalize provider codes and names.
- [ ] Normalize diagnostic-test names using a mapping table.
- [ ] Convert numeric fields safely.
- [ ] Handle suppression or missing-value markers explicitly.
- [ ] Separate waiting and activity records.
- [ ] Load data into staging tables.
- [ ] Run validation queries.
- [ ] Promote valid records into production tables.
- [ ] Generate a machine-readable quality report.

### Required validation checks

- [ ] Expected columns are present.
- [ ] Reporting month is valid.
- [ ] Provider code is not empty for provider-level records.
- [ ] Test code is recognized.
- [ ] Counts are non-negative.
- [ ] Percentages are between 0 and 100.
- [ ] Duplicate-key rate is zero after defined aggregation.
- [ ] Row-count difference from source is explained.
- [ ] Unknown test-code rate is zero or documented.

### Deliverables

- Working deterministic ingestion script.
- Unit tests for parsing and normalization.
- Quality-report JSON.

### Acceptance gate

Running ingestion twice with the same source produces the same database state and does not duplicate records.

### Failure controls

- Use database transactions.
- Roll back on failed validation.
- Make the loader idempotent.
- Never silently coerce malformed values to zero.

---

## Step 4 — Convert ingestion into a Prefect pipeline

### Goal

Earn full ingestion points and make updates observable and repeatable.

### Actions

Create Prefect tasks for:

1. Discover source files.
2. Download files.
3. Calculate hashes.
4. Check whether a file was already ingested.
5. Extract archives.
6. Validate schemas.
7. Load staging tables.
8. Normalize records.
9. Run data-quality tests.
10. Promote valid data.
11. Build derived metrics.
12. Generate provider profiles.
13. Build embeddings.
14. Save ingestion metrics.
15. Notify or log failure.

Configure:

- Retries with exponential backoff for downloads.
- Timeouts.
- Structured logging.
- Manual backfill parameters.
- A scheduled run.
- A dry-run mode.

### Deliverables

- `ingestion/flows.py`.
- Prefect deployment definition.
- Screenshot of a successful pipeline.
- Screenshot or test evidence for a controlled failure and retry.

### Acceptance gate

A clean environment can run one command to ingest a selected period and produce:

- Structured database records.
- Quality report.
- Provider profiles.
- Embeddings.

### Failure controls

- Fail closed when the schema changes.
- Do not delete the last good dataset when a new run fails.
- Store pipeline state and error details.

---

## Step 5 — Calculate trustworthy derived metrics

### Goal

Provide analytical value without asking the LLM to calculate.

### Actions

Implement and test:

- [ ] Long-wait percentage.
- [ ] Month-over-month waiting-list change.
- [ ] Year-over-year waiting-list change.
- [ ] Month-over-month activity change.
- [ ] Year-over-year activity change.
- [ ] Pressure proxy: waiting-list growth minus activity growth.
- [ ] Persistent pressure: number of months above a documented threshold.
- [ ] Data completeness score.
- [ ] Project-specific bottleneck score.

### Bottleneck-score rule

Start with:

```text
30% long-wait percentage
25% waiting-list growth
20% activity imbalance
15% persistence
10% CDC activity/capacity indicator
```

Normalize all components to 0–100 before combining them.

Create at least three weighting scenarios:

- Balanced.
- Waiting-focused.
- Capacity-focused.

### Deliverables

- Metric library.
- Metric definitions in `docs/data_dictionary.md`.
- Unit tests using hand-calculated examples.
- Sensitivity-analysis report.

### Acceptance gate

- Every formula has a test.
- Every displayed metric has a written definition.
- Score ranking changes across weighting scenarios are measured.
- The UI clearly says the bottleneck score is not an official NHS metric.

### Failure controls

- Guard against division by zero.
- Suppress percentage change when the baseline is zero.
- Expose missing or incomplete months.
- Never treat missing data as zero.

---

## Step 6 — Generate the RAG corpus

### Goal

Turn tabular data into useful explanatory documents without losing numerical traceability.

### Actions

Create four document types.

#### A. Provider-test profiles

Generate one profile for a defined period, such as the latest 12 months:

```text
Provider: [name]
Diagnostic service: [test]
Period: [start] to [end]

The waiting list changed from X to Y.
The percentage waiting six weeks or longer changed from A% to B%.
Monthly activity changed by C%.
CDC activity was D where available.

Interpretation:
[Rule-based explanation]

Limitations:
[Missing months, revisions, non-causal warning]
```

#### B. Diagnostic-test profiles

Explain each supported test, counting rules, and limitations.

#### C. Metric definitions

Explain every metric and formula.

#### D. Methodology and quality documents

Index relevant official guidance and your own methodology documentation.

Add metadata:

```json
{
  "document_id": "...",
  "document_type": "provider_profile",
  "provider_code": "...",
  "diagnostic_test": "MRI",
  "period_start": "...",
  "period_end": "...",
  "source_file_ids": ["..."],
  "quality_flag": "complete",
  "version": "..."
}
```

### Deliverables

- Profile-generation code.
- `documents` and `document_chunks` tables.
- Reproducible corpus build.
- Sample profiles reviewed manually.

### Acceptance gate

- Every profile number can be traced to SQL results.
- Regenerating the corpus does not create uncontrolled duplicates.
- Profiles clearly distinguish measured facts from interpretation.

### Failure controls

- Generate facts with code, not the LLM.
- Use templates for numerical sentences.
- Include reporting periods in every profile.

---

## Step 7 — Implement baseline retrieval

### Goal

Create measurable retrieval systems before adding complexity.

### Actions

Implement independently:

1. PostgreSQL full-text search.
2. Dense vector search with pgvector.
3. Hybrid search.

Use separate retrieval functions with the same interface:

```python
retrieve(query, filters, top_k) -> list[RetrievedDocument]
```

Add metadata filters for:

- Provider.
- Diagnostic test.
- Document type.
- Reporting period.

Create a hybrid method using either:

- Reciprocal Rank Fusion, or
- Normalized weighted score.

Prefer Reciprocal Rank Fusion initially because keyword and vector scores are not naturally comparable.

### Deliverables

- Three retrieval implementations.
- Retrieval logs.
- Unit tests.

### Acceptance gate

Each method returns deterministic top results for a fixed index and query.

### Failure controls

- Do not select the final method based on intuition.
- Log query, filters, document IDs, ranks, and scores.

---

## Step 8 — Build retrieval ground truth and evaluate

### Goal

Earn full retrieval-evaluation points with defensible evidence.

### Actions

Create 120–150 questions:

- 25 provider-profile questions.
- 20 test-definition questions.
- 20 metric-definition questions.
- 20 methodology questions.
- 20 comparison-support questions.
- 15 unanswerable questions.

For every question, store:

```json
{
  "question_id": "q001",
  "question": "What does waiting six weeks or longer mean?",
  "relevant_document_ids": ["metric-wait-6-plus"],
  "document_type": "metric_definition",
  "answerable": true
}
```

Evaluate:

- Hit Rate@5.
- MRR.
- Recall@5.
- Recall@10.
- NDCG@5.

Compare:

- Full-text.
- Dense vector.
- Hybrid.
- Hybrid plus reranking after Step 9.

### Deliverables

- `retrieval_ground_truth.jsonl`.
- Evaluation script.
- CSV and Markdown results.
- Error-analysis document.

### Acceptance gate

- Multiple approaches are evaluated on the same questions.
- The best measured approach is configured as the production default.
- At least 20 retrieval errors are manually categorized.

### Failure controls

- Freeze the evaluation set before tuning final weights.
- Keep a small untouched test split.
- Do not create ground truth automatically without manual review.

---

## Step 9 — Add document reranking

### Goal

Satisfy the reranking best practice and improve precision.

### Actions

- [ ] Retrieve the top 20 candidates using hybrid search.
- [ ] Rerank with a cross-encoder or LLM-based reranker.
- [ ] Return the best 5–8 documents.
- [ ] Measure latency and retrieval improvement.
- [ ] Add a timeout and fallback to hybrid order.

### Deliverables

- Reranking module.
- Evaluation comparison.
- Latency report.

### Acceptance gate

Use reranking in production only when it improves the chosen retrieval metric without unacceptable latency.

### Failure controls

- Cache repeated reranking requests.
- Keep a deterministic fallback.
- Do not send sensitive or unnecessary data to external models.

---

## Step 10 — Implement query rewriting and intent classification

### Goal

Convert user language into explicit, validated parameters.

### Actions

Define intents:

- `definition_lookup`.
- `provider_profile`.
- `compare_providers`.
- `rank_providers`.
- `trend_analysis`.
- `cdc_analysis`.
- `capacity_scenario`.
- `methodology_question`.
- `unsupported_medical_request`.

Extract:

- Provider names or codes.
- Diagnostic test.
- Metric.
- Start and end date.
- Number of results.
- Sort direction.
- Comparison entities.

Return a typed object validated with Pydantic.

Example:

```json
{
  "intent": "rank_providers",
  "diagnostic_test": "MRI",
  "metric": "percentage_waiting_6_plus_weeks",
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "sort_order": "descending",
  "limit": 10
}
```

### Deliverables

- Query-rewriting prompt.
- Pydantic schemas.
- Provider/test alias tables.
- Date-resolution utility.
- Test suite.

### Acceptance gate

On a manually reviewed set of at least 100 questions:

- Intent accuracy is measured.
- Provider resolution is measured.
- Test resolution is measured.
- Date extraction is measured.

### Failure controls

- Reject unknown metrics.
- Resolve ambiguous provider names visibly.
- Use absolute dates internally.
- Do not guess missing scenario parameters.

---

## Step 11 — Build controlled analytical tools

### Goal

Answer numerical questions exactly and safely.

### Required tools

- `get_provider_profile`.
- `compare_provider_waits`.
- `rank_provider_waits`.
- `analyze_waiting_trend`.
- `compare_activity_and_waiting`.
- `analyze_cdc_activity`.
- `find_similar_providers` as a phase-two feature.
- `simulate_capacity_change`.
- `retrieve_metric_definition`.

Each tool must:

- Accept a typed input schema.
- Validate provider and test codes.
- Use parameterized SQL.
- Return typed JSON.
- Include source periods and quality warnings.
- Log execution time and errors.

### Deliverables

- Tool module.
- Tool schemas.
- SQL query library.
- Unit and integration tests.

### Acceptance gate

- No tool accepts arbitrary SQL.
- All numeric values match direct SQL validation.
- Errors are returned in a structured form.

### Failure controls

- Use allowlisted metrics and sorting fields.
- Apply maximum date ranges and result limits.
- Add database query timeouts.

---

## Step 12 — Evaluate the agent

### Goal

Prove that the agent selects tools and arguments correctly.

### Actions

Create at least 100 cases containing:

- Question.
- Expected intent.
- Expected tool.
- Expected arguments.
- Expected result properties.

Measure:

- Intent accuracy.
- Tool-selection accuracy.
- Provider extraction accuracy.
- Diagnostic-test accuracy.
- Date accuracy.
- Metric accuracy.
- Exact result count.
- Numerical accuracy.
- Tool execution success.

Include difficult cases:

- Relative dates.
- Provider aliases.
- Similar test names.
- Missing parameters.
- Unsupported medical questions.
- Requests requiring both RAG and tools.

### Deliverables

- Agent test dataset.
- Evaluation script.
- Error analysis.

### Acceptance gate

The final README reports actual measured values and explains the most common failures.

### Failure controls

- Keep deterministic routing rules for obvious intents.
- Use the LLM only where language understanding adds value.

---

## Step 13 — Build grounded answer generation

### Goal

Produce readable answers without hallucinating facts or causality.

### Actions

Construct an evidence package containing:

- Tool result JSON.
- Retrieved passages.
- Source URLs.
- Reporting periods.
- Data-quality warnings.
- Required limitations.

Prompt rules:

- Use only supplied evidence.
- Never recalculate values.
- State the reporting period.
- Cite the source.
- Distinguish facts from inference.
- Use “associated with” rather than causal language.
- State when evidence is insufficient.
- Refuse individual medical advice.

Define a response structure:

```text
Answer
Key evidence
Interpretation
Limitations
Sources
```

### Deliverables

- Prompt templates.
- Citation formatter.
- Grounding checks.
- Example answers.

### Acceptance gate

Every factual number in a sample of 50 answers can be matched to a tool result.

### Failure controls

- Do not let the LLM introduce uncited numbers.
- Add a post-generation check for numerical tokens and source presence.
- Regenerate or fail safely when grounding checks fail.

---

## Step 14 — Evaluate LLM output

### Goal

Earn full LLM-evaluation points and select the best complete pipeline.

### Compare at least three configurations

- **A:** Dense retrieval + basic prompt.
- **B:** Query rewriting + hybrid retrieval.
- **C:** Query rewriting + analytical tools + hybrid retrieval + reranking + structured prompt.

### Evaluation dimensions

- Factual correctness.
- Numerical correctness.
- Groundedness.
- Citation correctness.
- Correct provider.
- Correct test.
- Correct period.
- Completeness.
- Clarity.
- Appropriate uncertainty.
- No unsupported causality.
- Correct refusal behavior.

Use:

- Programmatic checks for numbers and IDs.
- Human review for clarity and usefulness.
- Optional LLM judge with a documented rubric.

### Deliverables

- Answer evaluation dataset.
- Evaluation script.
- Comparison table.
- Selected production configuration.

### Acceptance gate

The production configuration is selected from measured results, not preference.

### Failure controls

- Do not rely only on an LLM judge.
- Manually audit low-scoring and high-scoring samples.
- Keep the evaluation prompt versioned.

---

## Step 15 — Build the Streamlit interface

### Goal

Provide a professional, demonstrable user experience.

### Required pages

#### 1. Ask ScanFlow

- Natural-language question.
- Interpreted query display.
- Answer.
- Supporting table or chart.
- Reporting period.
- Sources.
- Limitations.
- Feedback controls.

#### 2. Diagnostic Explorer

- Provider filter.
- Test filter.
- Date filter.
- Waiting trend.
- Activity trend.
- Long-wait percentage.

#### 3. Provider Comparison

- Select two to five providers.
- Compare the same test and period.
- Show normalized and absolute values.

#### 4. Bottleneck Ranking

- Region/provider scope.
- Test.
- Month or period.
- Score components.
- Data-quality filter.

#### 5. Capacity Scenario

- Current activity.
- Additional monthly activity.
- Assumed demand.
- Duration.
- Clear simplified-model warning.

#### 6. Methodology

- Data sources.
- Definitions.
- Score formula.
- Limitations.
- Evaluation results.

### Deliverables

- Streamlit application.
- Responsive layout.
- Screenshots.
- Short preview video.

### Acceptance gate

A new user can complete five documented tasks without reading the code.

### Failure controls

- Never hide source dates.
- Display warnings close to the result, not only in a footer.
- Use clear empty and error states.

---

## Step 16 — Implement feedback and monitoring

### Goal

Earn full monitoring points and create operational visibility.

### Feedback fields

- Helpful / not helpful.
- Incorrect provider.
- Incorrect number.
- Wrong interpretation.
- Missing source.
- Outdated data.
- Optional comment.

### Interaction log fields

```text
interaction_id
session_id
timestamp
question
rewritten_query
intent
tools_called
tool_success
retrieval_method
retrieved_document_ids
retrieval_scores
reranker_used
model_name
prompt_version
response_time_ms
prompt_tokens
completion_tokens
estimated_cost
answer
feedback
feedback_comment
```

### Grafana charts

Implement at least these five; preferably ten:

1. Questions per day.
2. Average and p95 response time.
3. Positive-feedback rate.
4. Tool success/failure rate.
5. Retrieval-score distribution.
6. Questions by diagnostic test.
7. Questions by intent.
8. Unanswerable or insufficient-evidence rate.
9. Ingestion freshness.
10. Estimated token cost.

### Deliverables

- Feedback API and table.
- Grafana datasource configuration.
- Dashboard JSON committed to the repository.
- Screenshots.

### Acceptance gate

A submitted question and feedback event appear in the dashboard.

### Failure controls

- Do not store user secrets.
- Sanitize comments.
- Add retention settings for logs if deployed.

---

## Step 17 — Containerize the complete system

### Goal

Earn full containerization and reproducibility points.

### Docker Compose services

- `frontend` — Streamlit.
- `backend` — FastAPI.
- `postgres` — PostgreSQL with pgvector.
- `prefect-server`.
- `prefect-worker`.
- `grafana`.

Optional:

- `prometheus` only if needed.

### Actions

- [ ] Create separate frontend and backend Dockerfiles.
- [ ] Add health checks.
- [ ] Add named volumes.
- [ ] Add database migrations on startup.
- [ ] Add dependency ordering based on health, not sleep commands.
- [ ] Add `.env.example`.
- [ ] Pin dependency versions.
- [ ] Add `make up`, `make ingest`, `make test`, and `make evaluate` commands.

### Acceptance gate

On a clean machine:

```bash
cp .env.example .env
docker compose up --build
```

starts the complete system, after which one documented ingestion command loads the sample or full dataset.

### Failure controls

- Test from a clean clone.
- Do not depend on local Python packages.
- Do not commit API keys.
- Provide an Ollama or mock mode if possible for reviewer convenience.

---

## Step 18 — Add automated testing and CI

### Goal

Prevent regressions and demonstrate professional engineering quality.

### Test layers

#### Unit tests

- Parsers.
- Normalization.
- Metrics.
- Query rewriting utilities.
- Tool validation.

#### Integration tests

- Database loading.
- Retrieval.
- Tool execution.
- Feedback logging.

#### End-to-end tests

- Ingest fixture data.
- Ask a known question.
- Verify tool call.
- Verify answer contains the expected source and period.

#### Data tests

- Schema presence.
- Range checks.
- Duplicate checks.
- Referential integrity.
- Row-count anomalies.

### CI actions

- Lint.
- Type check.
- Unit tests.
- Integration tests with temporary PostgreSQL.
- Docker build.
- Secret scan.

### Acceptance gate

The main branch passes CI from a clean checkout.

### Failure controls

- Keep test fixtures small and deterministic.
- Do not make every CI run call paid LLM APIs.
- Mock the LLM for most tests and run a small optional live test suite.

---

## Step 19 — Prepare reproducibility documentation

### Goal

Make the reviewer successful without private help.

### README mandatory sections

1. Project title.
2. Problem description.
3. Intended users.
4. Data sources and licence.
5. Scope and limitations.
6. Architecture.
7. Data ingestion.
8. Data model.
9. Retrieval flow.
10. Agent tools.
11. Query rewriting.
12. Retrieval evaluation.
13. Agent evaluation.
14. LLM evaluation.
15. Interface.
16. Monitoring and feedback.
17. Docker setup.
18. Local setup.
19. Environment variables.
20. Example questions.
21. Screenshots.
22. Deployment.
23. Known limitations.
24. Rubric checklist.

### Required setup commands

Document exact commands for:

- Clone.
- Environment setup.
- Docker startup.
- Database migration.
- Data ingestion.
- App access.
- Grafana access.
- Tests.
- Evaluation.
- Shutdown and cleanup.

### Acceptance gate

Ask another person to follow the README from a clean clone. Record and fix every point where they need to ask a question.

### Failure controls

- Do not write “run the application normally.”
- Include exact ports, credentials setup, and expected outputs.
- Pin versions in lock files or `requirements.txt`.

---

## Step 20 — Deployment and bonus work

### Goal

Earn deployment bonus without damaging the stable local project.

### Actions

- [ ] Deploy frontend and backend.
- [ ] Deploy PostgreSQL with pgvector.
- [ ] Configure secrets in the platform, not the repository.
- [ ] Use a scheduled ingestion job or document manual refresh.
- [ ] Add health endpoint and uptime check.
- [ ] Add a public demo-data mode if full ingestion is too heavy.
- [ ] Add deployment URL and architecture notes to README.

### Acceptance gate

The deployment works from a private/incognito browser and displays the source period.

### Failure controls

- Keep local Docker Compose as the source of truth.
- Never make the project dependent on the cloud deployment being alive.
- Set cost limits.

---

## Step 21 — Final rubric audit and submission freeze

### Goal

Submit a stable, reviewable commit rather than the latest experimental code.

### Actions

- [ ] Run all tests.
- [ ] Run all evaluations.
- [ ] Run a clean Docker build.
- [ ] Run ingestion from a clean database.
- [ ] Verify all screenshots reflect the submitted commit.
- [ ] Verify every README link.
- [ ] Verify no secret is in Git history.
- [ ] Verify dataset access instructions.
- [ ] Verify licences and attribution.
- [ ] Verify monitoring has at least five charts.
- [ ] Verify feedback is stored.
- [ ] Verify hybrid search, reranking, and query rewriting are active.
- [ ] Tag the final commit.
- [ ] Record the exact commit hash.
- [ ] Do not change the submission branch after recording the hash unless repeating the audit.

### Acceptance gate

A reviewer can:

1. Clone the exact commit.
2. Start the system.
3. Ingest data.
4. Ask sample questions.
5. Inspect evaluation results.
6. Inspect monitoring.
7. Verify every rubric item.

---

# 8. Professional task backlog

Use these as GitHub issues or project-board cards.

| ID | Professional task | Definition of done |
|---|---|---|
| DATA-01 | Register official data sources | Source, licence, update frequency, and download strategy documented. |
| DATA-02 | Inspect monthly diagnostic files | Real columns, dimensions, keys, and quality issues documented. |
| DATA-03 | Inspect CDC file | Provider identifiers and test categories documented. |
| DATA-04 | Build canonical data dictionary | Every used field has source, type, unit, definition, and null rule. |
| ING-01 | Implement diagnostic parser | Parses fixture and real monthly files with tests. |
| ING-02 | Implement CDC parser | Parses current provider CSV with tests. |
| ING-03 | Add validation framework | Schema, range, duplicate, and referential checks pass. |
| ING-04 | Build Prefect flow | End-to-end flow is idempotent and observable. |
| DB-01 | Create database migrations | Clean database can be created automatically. |
| MET-01 | Implement derived metrics | All formulas have unit tests. |
| MET-02 | Implement bottleneck score | Score and sensitivity report documented. |
| RAG-01 | Generate provider profiles | Profiles are traceable and reproducible. |
| RAG-02 | Build full-text retrieval | Results and scores logged. |
| RAG-03 | Build vector retrieval | Embedding model and version documented. |
| RAG-04 | Build hybrid retrieval | Fusion method implemented and evaluated. |
| RAG-05 | Add reranker | Improvement and latency measured. |
| AGT-01 | Define intents and schemas | Typed contracts committed. |
| AGT-02 | Implement query rewriting | Accuracy measured on a labeled set. |
| AGT-03 | Implement analytical tools | All tools use parameterized SQL and typed results. |
| AGT-04 | Evaluate agent | Tool and argument accuracy reported. |
| LLM-01 | Build evidence prompt | Answer uses only supplied facts. |
| LLM-02 | Add grounding validation | Uncited or inconsistent numbers are detected. |
| LLM-03 | Evaluate answer pipelines | At least two approaches compared. |
| UI-01 | Build Ask ScanFlow | Complete answer, sources, periods, and feedback displayed. |
| UI-02 | Build Diagnostic Explorer | Filters and trend charts work. |
| UI-03 | Build Provider Comparison | Same-period comparison works. |
| UI-04 | Build Capacity Scenario | Simplified scenario with warning works. |
| MON-01 | Log interactions | Required fields stored. |
| MON-02 | Collect feedback | Feedback appears in the database. |
| MON-03 | Build Grafana dashboard | At least five committed charts work. |
| OPS-01 | Create Docker Compose | All required services start. |
| OPS-02 | Add CI | Tests and Docker builds pass. |
| DOC-01 | Complete README | All rubric sections and commands are present. |
| DOC-02 | Record demo | Short walkthrough matches final commit. |
| REL-01 | Run submission audit | Checklist signed off against exact commit hash. |

---

# 9. Evaluation targets

These are recommended internal quality targets, not promises to reviewers.

| Area | Recommended target |
|---|---:|
| Retrieval Hit Rate@5 | At least 0.85 |
| Retrieval MRR | At least 0.70 |
| Intent accuracy | At least 0.90 |
| Tool-selection accuracy | At least 0.90 |
| Provider/test extraction accuracy | At least 0.95 on supported scope |
| Numerical accuracy | 100% against SQL for supported questions |
| Citation presence | 100% for factual answers |
| Positive test-suite pass rate | 100% |
| Unsupported medical-request refusal | 100% on safety test set |
| Docker smoke test | Pass from clean clone |

If a target is not reached, report the actual result honestly and document the error analysis.

---

# 10. Risk register

| Risk | Impact | Prevention | Contingency |
|---|---|---|---|
| Source schema changes | Ingestion fails or corrupts data | Expected-schema validation and fail-closed behavior | Keep last good dataset and update mappings |
| Revised NHS files | Results change after ingestion | File hashes, revision metadata, immutable source registry | Re-ingest and regenerate profiles |
| Provider-code changes | Broken joins | Versioned provider dimension | Map successor and predecessor codes |
| Missing months | Incorrect trend conclusions | Completeness checks and visible warnings | Restrict analysis to complete periods |
| LLM invents numbers | Loss of trust | Tool-only numbers and post-generation validation | Fail safely and show tool output directly |
| Retrieval returns wrong provider | Wrong explanation | Metadata filtering and provider resolution | Ask user to choose from matched providers in UI |
| Score seems official | Misleading interpretation | Persistent label: project-specific score | Show raw components instead of score |
| CDC association interpreted as causation | Invalid conclusion | Prompt and UI non-causal language | Remove causal statements during grounding check |
| Project scope becomes too large | Incomplete submission | Mandatory MVP freeze | Drop RTT/workforce/stretch features |
| Cloud deployment fails | Bonus lost | Local Docker remains complete | Submit local reproducible project |
| Reviewer cannot run paid LLM | Reproducibility loss | Support configurable provider and demo/mock mode | Include cached demo responses only for walkthrough, not evaluation |
| Data licence confusion | Documentation issue | Use official source pages and OGL attribution | Exclude any source with unclear terms |

---

# 11. Suggested milestone schedule

Adjust the duration to your available calendar, but preserve the order.

## Milestone 1 — Foundation

- Project contract.
- Source discovery.
- Data dictionary.
- Database design.

**Exit condition:** three real monthly files load manually and are understood.

## Milestone 2 — Reliable ingestion

- Deterministic loader.
- Validation.
- Prefect pipeline.
- Source lineage.

**Exit condition:** idempotent ingestion passes quality checks.

## Milestone 3 — Analytics vertical slice

- Derived metrics.
- One provider/test trend tool.
- Basic FastAPI endpoint.
- Basic Streamlit answer.

**Exit condition:** one question produces a validated result and source period.

## Milestone 4 — RAG

- Provider profiles.
- Definitions.
- Full-text and vector search.
- Retrieval ground truth.

**Exit condition:** retrieval evaluation runs reproducibly.

## Milestone 5 — Agent

- Query rewriting.
- Controlled tools.
- Agent evaluation.

**Exit condition:** supported questions route correctly and numbers match SQL.

## Milestone 6 — Quality and UX

- Reranker.
- LLM evaluation.
- Full Streamlit pages.
- Feedback.

**Exit condition:** production configuration selected from evaluation.

## Milestone 7 — Operations

- Grafana.
- Docker Compose.
- CI.
- Clean-clone test.

**Exit condition:** full environment starts from documented commands.

## Milestone 8 — Submission

- README.
- Screenshots.
- Demo video.
- Rubric audit.
- Commit freeze.

**Exit condition:** independent reviewer completes setup successfully.

---

# 12. Sample acceptance questions for the final application

Use these for demos and end-to-end tests:

1. What does “waiting six weeks or longer” mean?
2. Show the MRI long-wait trend for a selected provider over the latest 12 complete months.
3. Compare MRI waiting performance between two selected providers during the same period.
4. Which five providers have the highest MRI long-wait percentage in the latest complete month?
5. Which supported diagnostic service has the highest persistent pressure for a selected provider?
6. Did CT activity grow faster than the CT waiting list for a selected provider?
7. How has Community Diagnostic Centre activity changed for a selected provider?
8. Explain the evidence behind the bottleneck score.
9. What information is missing for this provider-period comparison?
10. What would a simplified increase of 200 MRI procedures per month do to the waiting-list balance, assuming demand stays constant?
11. Should an individual patient receive an MRI sooner? Expected behavior: refuse individual clinical prioritization and explain the application’s aggregate scope.

---

# 13. Final submission checklist

## Data

- [ ] Official publication links work.
- [ ] Source periods are documented.
- [ ] File hashes and revisions are stored.
- [ ] Raw data is not silently modified.
- [ ] Licence attribution is present.

## Application

- [ ] RAG knowledge base is used.
- [ ] LLM is used.
- [ ] Analytical tools are used.
- [ ] Numerical answers come from tools.
- [ ] Sources and reporting periods are displayed.
- [ ] Unsupported medical requests are refused.

## Evaluation

- [ ] Multiple retrieval approaches are compared.
- [ ] Best retrieval approach is used.
- [ ] Reranking is evaluated.
- [ ] Query rewriting is evaluated.
- [ ] Agent tool selection is evaluated.
- [ ] Multiple answer-generation approaches are compared.
- [ ] Numerical accuracy is programmatically checked.
- [ ] Error analysis is documented.

## Interface and monitoring

- [ ] Streamlit UI works.
- [ ] Feedback is stored.
- [ ] Grafana has at least five charts.
- [ ] Screenshots are current.
- [ ] Preview video is current.

## Engineering

- [ ] Everything runs in Docker Compose.
- [ ] Dependencies are pinned.
- [ ] `.env.example` is complete.
- [ ] No secrets are committed.
- [ ] CI passes.
- [ ] Clean-clone smoke test passes.

## Documentation

- [ ] README follows rubric headings.
- [ ] Architecture is shown.
- [ ] Setup is exact.
- [ ] Example questions are included.
- [ ] Limitations are explicit.
- [ ] Evaluation tables contain real results.
- [ ] Exact commit hash is recorded.
- [ ] Three peer reviews are completed as required by the course.

---

# 14. Final professional recommendation

The safest route to a high score is not to implement every possible dataset. Complete the following vertical slice first:

> Download diagnostic and CDC data, validate and store it, calculate exact metrics, generate provider profiles, retrieve definitions with hybrid RAG, route questions to controlled analytical tools, return cited answers in Streamlit, evaluate every layer, log feedback, display Grafana monitoring, and run the entire system with Docker Compose.

Only add RTT, workforce, maps, or advanced simulation after this vertical slice passes all acceptance gates.

The project should be presented as a healthcare-operations intelligence application, not a clinical system. Its value is the combination of reproducible public data analysis, natural-language access, explainable retrieval, and transparent limitations.
