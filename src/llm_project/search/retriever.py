"""Single dispatch point for all retrieval approaches, used by both the eval scripts
and the RAG/agent pipeline so "the best one" (per retrieval_eval_results.csv) can be
swapped in by changing one string.
"""

from llm_project.search import minsearch_index
from llm_project.search.rerank import rerank as rerank_docs

METHODS = ["minsearch_text", "minsearch_vector", "es_text", "es_knn", "es_hybrid", "es_hybrid_rerank"]


def retrieve(query: str, method: str = "es_hybrid_rerank", num_results: int = 5) -> list[dict]:
    if method == "minsearch_text":
        return minsearch_index.search_text(query, num_results=num_results)
    if method == "minsearch_vector":
        return minsearch_index.search_vector(query, num_results=num_results)

    from llm_project.search import es_index  # lazy: only needed when an ES-backed method is used

    es = es_index.get_client()

    if method == "es_text":
        return es_index.search_text(es, query, num_results=num_results)
    if method == "es_knn":
        return es_index.search_knn(es, query, num_results=num_results)
    if method == "es_hybrid":
        return es_index.search_hybrid(es, query, num_results=num_results)
    if method == "es_hybrid_rerank":
        candidates = es_index.search_hybrid(es, query, num_results=num_results * 4)
        return rerank_docs(query, candidates, top_k=num_results)

    raise ValueError(f"Unknown retrieval method: {method!r}, expected one of {METHODS}")
