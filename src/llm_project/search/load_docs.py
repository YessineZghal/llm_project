import json
from functools import lru_cache

from llm_project.config import RAW_DOCS_PATH


@lru_cache(maxsize=1)
def load_docs() -> list[dict]:
    if not RAW_DOCS_PATH.exists():
        raise FileNotFoundError(
            f"{RAW_DOCS_PATH} not found — run `uv run python -m llm_project.ingest.pipeline` first."
        )
    with open(RAW_DOCS_PATH) as f:
        return [json.loads(line) for line in f]
