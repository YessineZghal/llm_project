.PHONY: up down build bootstrap grafana ingest metrics corpus index test test-unit test-integration lint app \
	evaluate evaluate-retrieval evaluate-agent evaluate-grounding evaluate-pipelines

up:
	docker compose up --build -d app elasticsearch app_postgres grafana

down:
	docker compose down

# Grafana alone (e.g. after `make bootstrap`, before starting the app itself).
grafana:
	docker compose up -d app_postgres grafana

build:
	docker compose build app

# First-time setup on a clean checkout: start the data services, load a real
# month of NHS data, compute derived metrics, generate and index the RAG
# corpus. Does not start the `app` container - run `make app` (local) or
# `make up` (containerized) once this finishes. Safe to re-run: ingestion is
# idempotent (src/llm_project/ingest/nhs_pipeline.py hashes and dedupes
# source files) and index/corpus generation is a full rebuild each time.
bootstrap:
	docker compose up -d elasticsearch app_postgres
	uv run python -m llm_project.ingest.nhs_discovered_run
	uv run python -m llm_project.analytics.metrics
	uv run python -m llm_project.rag.generate_corpus
	uv run python -m llm_project.search.es_index --recreate
	@echo "Bootstrap complete. Run 'make app' or 'make up' to start the application."

# Ingest the current NHS publication-year's files and recompute derived metrics.
# For a specific historical backfill, call nhs_pipeline directly with explicit URLs
# (see README.md "Manual setup" / DATA_SOURCES.md).
ingest:
	uv run python -m llm_project.ingest.nhs_discovered_run
	uv run python -m llm_project.analytics.metrics

metrics:
	uv run python -m llm_project.analytics.metrics

# Regenerate the RAG corpus from current database facts, then rebuild the
# Elasticsearch index from it (requires elasticsearch running).
corpus:
	uv run python -m llm_project.rag.generate_corpus

index:
	uv run python -m llm_project.search.es_index --recreate

test-unit:
	uv run pytest tests/unit/ -v

# Requires app_postgres running with data already loaded.
test-integration:
	uv run pytest tests/integration/ -v

test: test-unit test-integration

lint:
	uv run ruff check src tests || true

app:
	uv run streamlit run src/llm_project/app/streamlit_app.py

evaluate-retrieval:
	uv run python -m llm_project.eval.evaluate_retrieval

# Slower (many LLM calls); see evaluate_agent.py's rate-limit retry/backoff.
evaluate-agent:
	uv run python -m llm_project.eval.evaluate_agent

# plan.md Step 13's acceptance gate: numeric grounding over a real 50-answer sample.
evaluate-grounding:
	uv run python -m llm_project.eval.evaluate_grounding

# plan.md Step 14: 3-way pipeline comparison (dense-only vs rewriting+hybrid vs full agent).
evaluate-pipelines:
	uv run python -m llm_project.eval.evaluate_llm_pipelines

evaluate: evaluate-retrieval evaluate-agent evaluate-grounding evaluate-pipelines
