"""In-memory retrieval approach #1: minsearch (course library), text and vector modes."""

from functools import lru_cache

import minsearch

from llm_project.search.embeddings import embed_docs_cached, embed_query
from llm_project.search.load_docs import load_docs


@lru_cache(maxsize=1)
def get_text_index() -> minsearch.Index:
    docs = load_docs()
    index = minsearch.Index(
        text_fields=["title", "abstract", "authors"],
        keyword_fields=["id", "categories", "source_topic"],
    )
    index.fit(docs)
    return index


@lru_cache(maxsize=1)
def get_vector_index() -> minsearch.VectorSearch:
    docs = load_docs()
    vectors = embed_docs_cached(docs)
    vs = minsearch.VectorSearch()
    vs.fit(vectors, docs)
    return vs


def search_text(query: str, num_results: int = 5) -> list[dict]:
    index = get_text_index()
    return index.search(query, num_results=num_results)


def search_vector(query: str, num_results: int = 5) -> list[dict]:
    vs = get_vector_index()
    query_vector = embed_query(query)
    return vs.search(query_vector, num_results=num_results)
