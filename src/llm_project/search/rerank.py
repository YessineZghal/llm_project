"""Cross-encoder reranking, applied on top of a first-pass retrieval (best-practices criterion)."""

from functools import lru_cache

from llm_project.config import RERANK_MODEL_NAME
from llm_project.search.embeddings import doc_text


@lru_cache(maxsize=1)
def get_reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANK_MODEL_NAME)


def rerank(query: str, docs: list[dict], top_k: int = 5) -> list[dict]:
    if not docs:
        return []
    reranker = get_reranker()
    pairs = [(query, doc_text(d)) for d in docs]
    scores = reranker.predict(pairs)
    scored = sorted(zip(docs, scores), key=lambda pair: pair[1], reverse=True)
    return [{**doc, "_rerank_score": float(score)} for doc, score in scored[:top_k]]
