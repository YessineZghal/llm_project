import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
EVAL_DIR = DATA_DIR / "eval"
QUALITY_REPORTS_DIR = DATA_DIR / "quality_reports"

RAW_DOCS_PATH = RAW_DIR / "documents.jsonl"  # RAG corpus (provider profiles, definitions, ...) - built in Milestone 4
GROUND_TRUTH_PATH = EVAL_DIR / "retrieval_ground_truth.jsonl"
RETRIEVAL_EVAL_RESULTS_PATH = EVAL_DIR / "retrieval_eval_results.csv"
RETRIEVAL_ERROR_ANALYSIS_PATH = EVAL_DIR / "retrieval_error_analysis.md"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
RERANK_MODEL_NAME = os.getenv("RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

ELASTIC_URL = os.getenv("ELASTIC_URL", "http://localhost:9200")
ELASTIC_INDEX_NAME = os.getenv("ELASTIC_INDEX_NAME", "scanflow-documents")

POSTGRES_HOST = os.getenv("APP_POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("APP_POSTGRES_PORT", "5433")
POSTGRES_DB = os.getenv("APP_POSTGRES_DB", "llm_project")
POSTGRES_USER = os.getenv("APP_POSTGRES_USER", "llm_project")
POSTGRES_PASSWORD = os.getenv("APP_POSTGRES_PASSWORD", "llm_project")

POSTGRES_URL = (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

for _dir in (DATA_DIR, RAW_DIR, EVAL_DIR, QUALITY_REPORTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
