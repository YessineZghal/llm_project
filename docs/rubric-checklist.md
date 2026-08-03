# Rubric checklist

The DataTalksClub LLM Zoomcamp grading rubric (from `project.md`), tracked
against current implementation status. Updated as milestones land; see
`agent/PROGRESS.md` for the detailed, continuously updated build log.

## Problem description

- 0 points: the problem is not described
- 2 points: the problem is well described and it is clear what problem the project solves

Status: complete. Described in `README.md` ("Problem statement").

## Retrieval flow

- 0 points: no knowledge base or LLM is used
- 2 points: both a knowledge base and an LLM are used in the flow

Status: complete. A 1,870-document knowledge base
(`src/llm_project/rag/generate_corpus.py`, indexed via
`src/llm_project/search/`) and an OpenAI-backed agent
(`src/llm_project/rag/agent.py`) are both used - the agent routes between
knowledge-base retrieval and controlled analytical tools depending on the
question. Numerical answers still come only from tools, never from the
model directly, by design.

## Retrieval evaluation

- 0 points: no evaluation of retrieval is provided
- 2 points: multiple retrieval approaches are evaluated, and the best one is used

Status: complete. Six approaches evaluated (minsearch text/vector,
Elasticsearch text/kNN/hybrid, hybrid with reranking) against a 120-question
stratified ground truth, computing Hit Rate@5/MRR/Recall@5/Recall@10/NDCG@5.
`es_hybrid_rerank` wins (MRR 0.948) and is the default in
`src/llm_project/search/retriever.py`. Results:
`data/eval/retrieval_eval_results.csv`.

## LLM evaluation

- 0 points: no evaluation of final LLM output is provided
- 2 points: multiple approaches are evaluated, and the best one is used

Status: partial. The agent has been evaluated end to end (117 real cases:
92.3% intent accuracy, 100% refusal correctness on safety cases) - see
`data/eval/agent_eval_results.csv`. What's missing for full credit here: a
formal comparison of multiple distinct answer-generation *pipelines*
(plan.md Step 14's A/B/C: dense+basic / rewriting+hybrid / full pipeline),
since currently only one pipeline configuration exists to evaluate.

## Interface

- 0 points: no way to interact with the application at all
- 2 points: UI, web application, or an API

Status: complete. Seven Streamlit pages: a chat interface backed by the
agent (Ask ScanFlow), two tool-direct structured-lookup views (Rank
providers, Provider profile), and four dedicated chart-based analysis
pages (Diagnostic Explorer, Provider Comparison, Bottleneck Ranking,
Capacity Scenario), plus Monitoring and Methodology. Feedback collection
works across all interactive views.

## Ingestion pipeline

- 0 points: no ingestion
- 2 points: automated ingestion with a special tool (Kestra, dlt, Airflow, Prefect, etc.)

Status: complete. Deterministic, idempotent, self-discovering ingestion
(`src/llm_project/ingest/`), orchestrated by Kestra
(`flows/ingest_diagnostics.yaml`), verified running end to end in a live
Kestra instance (not just as a standalone script).

## Monitoring

- 0 points: no monitoring
- 1 point: user feedback is collected, or there is a monitoring dashboard
- 2 points: user feedback is collected and there is a dashboard with at least five charts

Status: complete. Feedback collection verified end to end. The monitoring
dashboard (`src/llm_project/app/pages/1_Monitoring.py`) has six charts:
interaction volume over time, interactions by mode, questions by
diagnostic test, response time distribution, feedback breakdown, and
most-cited source documents - all reflecting real current interaction
data (mode/chart definitions were corrected mid-project after an earlier
version referenced a prior project phase's categories).

## Containerization

- 0 points: no containerization
- 2 points: everything is in docker-compose

Status: complete for the services implemented. `docker-compose.yml`
covers the application, its database, Elasticsearch, and Kestra with its
own database, with health checks and dependency ordering.
`elasticsearch`/`app_postgres` are bound to `127.0.0.1` only and
`app_postgres` requires a real password with no built-in default (see
README "Security").

## Reproducibility

- 0 points: no instructions on how to run the code, the data is missing, or it is unclear how to access it
- 2 points: instructions are clear, the dataset is accessible, it is easy to run the code, and it works; versions for all dependencies are specified

Status: complete. Dependencies pinned via `uv.lock`. Setup instructions
(Docker Compose, manual, Kestra-orchestrated) in `README.md` have been
executed and verified during development. Source data is publicly
accessible; its exact location is in `DATA_SOURCES.md`. CI
(`.github/workflows/ci.yml`) runs lint, both test suites, a Docker build,
and a secret scan on every push - written and YAML-validated, but not yet
run on a real GitHub Actions runner (no such runner available during
development; worth confirming once pushed).

## Best practices

- Hybrid search: complete - `es_hybrid` combines BM25 and kNN via Reciprocal Rank Fusion, evaluated above.
- Document reranking: complete - `es_hybrid_rerank` (cross-encoder reranking) is the evaluated winner and default.
- User query rewriting: complete - `src/llm_project/rag/query_rewrite.py` (search-query rewriting) and `src/llm_project/rag/intent.py` (intent/entity extraction with code-side validation, not trusted from the LLM).

## Bonus points

- Deployment to the cloud: not attempted, deliberately deferred (plan.md Step 20, explicitly a bonus item that should not put the core local, reproducible project at risk).
- Other: automated, self-discovering ingestion that scrapes NHS England's live publication pages rather than depending on hardcoded file URLs; every numerical fact is traceable to a specific source file via a foreign key; the entire RAG corpus is template-generated from validated database facts with zero LLM calls; a bottleneck-score ranking tool with three weighting scenarios and a component-level breakdown chart, so the composite score is explainable rather than opaque; a documented, verified security review of the LLM-controlled tool-call surface (see README "Security").
