# Rubric checklist

The DataTalksClub LLM Zoomcamp grading rubric (from `project.md`), tracked
against current implementation status. Updated as milestones land; see
`agent/PROGRESS.md` for the detailed, continuously updated build log.

## Problem description

- 0 points: the problem is not described
- 2 points: the problem is well described and it is clear what problem the project solves

Status: described in `README.md` ("Problem statement").

## Retrieval flow

- 0 points: no knowledge base or LLM is used
- 2 points: both a knowledge base and an LLM are used in the flow

Status: not yet implemented. Planned for Milestone 4 (knowledge base) and
Milestone 6 (LLM-generated grounded answers). The current interface uses
only deterministic analytical tools, by design, per the project's
principle that numerical answers must never come from a model.

## Retrieval evaluation

- 0 points: no evaluation of retrieval is provided
- 2 points: multiple retrieval approaches are evaluated, and the best one is used

Status: not yet implemented. Planned for Milestone 4. The retrieval layer
itself (`src/llm_project/search/`, six approaches: minsearch text and
vector, Elasticsearch text/kNN/hybrid, and hybrid with reranking) already
exists and was evaluated in an earlier phase of this project against a
different corpus; Milestone 4 repoints it at the NHS-derived corpus and
re-evaluates.

## LLM evaluation

- 0 points: no evaluation of final LLM output is provided
- 2 points: multiple approaches are evaluated, and the best one is used

Status: not yet implemented. Planned for Milestone 6.

## Interface

- 0 points: no way to interact with the application at all
- 2 points: UI, web application, or an API

Status: complete. Streamlit interface at
`src/llm_project/app/streamlit_app.py`, functional for the tools
implemented so far (provider ranking, provider profile), with feedback
collection.

## Ingestion pipeline

- 0 points: no ingestion
- 2 points: automated ingestion with a special tool (Kestra, dlt, Airflow, Prefect, etc.)

Status: complete. Deterministic, idempotent, self-discovering ingestion
(`src/llm_project/ingest/`), orchestrated by Kestra
(`flows/ingest_diagnostics.yaml`), verified running end to end in a live
Kestra instance.

## Monitoring

- 0 points: no monitoring
- 1 point: user feedback is collected, or there is a monitoring dashboard
- 2 points: user feedback is collected and there is a dashboard with at least five charts

Status: partial. Feedback collection is implemented and verified
end to end. A monitoring dashboard exists
(`src/llm_project/app/pages/1_Monitoring.py`) with six charts; two of
those charts (mode split, retrieval method usage) reference concepts from
an earlier phase of the project and will be updated once the agent and
retrieval layers are live in Milestones 4 to 6, so the chart set reflects
what the application actually does end to end.

## Containerization

- 0 points: no containerization
- 2 points: everything is in docker-compose

Status: complete for the services implemented so far. `docker-compose.yml`
covers the application, its database, Elasticsearch, and Kestra with its
own database, with health checks and dependency ordering.

## Reproducibility

- 0 points: no instructions on how to run the code, the data is missing, or it is unclear how to access it
- 2 points: instructions are clear, the dataset is accessible, it is easy to run the code, and it works; versions for all dependencies are specified

Status: complete. Dependencies are pinned via `uv.lock`. Setup
instructions (Docker Compose, manual, and Kestra-orchestrated) are in
`README.md` and have been executed and verified during development, not
only written. Source data is publicly accessible and its exact location
is documented in `DATA_SOURCES.md`.

## Best practices

- Hybrid search: combining vector and keyword search (already implemented in the retrieval layer, not yet re-evaluated against the NHS corpus - Milestone 4)
- Document reranking (already implemented in the retrieval layer, not yet re-evaluated against the NHS corpus - Milestone 4)
- User query rewriting (planned, Milestone 5)

## Bonus points

- Deployment to the cloud: not attempted, deliberately deferred (plan.md Step 20, explicitly a bonus item that should not put the core local, reproducible project at risk)
- Other: automated, self-discovering ingestion that scrapes NHS England's live publication pages rather than depending on hardcoded file URLs; every numerical fact in the application is traceable to a specific source file via a foreign key, and every derived table is fully recomputable rather than hand-maintained
