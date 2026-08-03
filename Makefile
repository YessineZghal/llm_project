.PHONY: up down build ingest metrics corpus index test test-unit test-integration lint app evaluate evaluate-retrieval evaluate-agent

up:
	docker compose up --build -d app elasticsearch app_postgres

down:
	docker compose down

build:
	docker compose build app

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

evaluate: evaluate-retrieval evaluate-agent
