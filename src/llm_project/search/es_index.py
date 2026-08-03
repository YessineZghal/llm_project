"""In-memory retrieval approaches #2/#3: Elasticsearch text (BM25), kNN (dense vector), and a
hybrid of the two combined client-side via Reciprocal Rank Fusion (best-practices criterion).
"""

from elasticsearch import Elasticsearch

from llm_project.config import ELASTIC_INDEX_NAME, ELASTIC_URL
from llm_project.search.embeddings import embed_docs_cached, embed_query
from llm_project.search.load_docs import load_docs

VECTOR_DIMS = 384  # sentence-transformers/all-MiniLM-L6-v2

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "title": {"type": "text"},
            "abstract": {"type": "text"},
            "authors": {"type": "text"},
            "categories": {"type": "keyword"},
            "source_topic": {"type": "keyword"},
            "url": {"type": "keyword"},
            "published": {"type": "keyword"},
            "text_vector": {
                "type": "dense_vector",
                "dims": VECTOR_DIMS,
                "index": True,
                "similarity": "cosine",
            },
        }
    }
}


def get_client() -> Elasticsearch:
    return Elasticsearch(ELASTIC_URL, request_timeout=30)


def index_exists(es: Elasticsearch, index_name: str = ELASTIC_INDEX_NAME) -> bool:
    return es.indices.exists(index=index_name)


def build_index(es: Elasticsearch, index_name: str = ELASTIC_INDEX_NAME, recreate: bool = False) -> int:
    if es.indices.exists(index=index_name):
        if not recreate:
            return es.count(index=index_name)["count"]
        es.indices.delete(index=index_name)

    es.indices.create(index=index_name, body=INDEX_MAPPING)

    docs = load_docs()
    vectors = embed_docs_cached(docs)

    from elasticsearch.helpers import bulk

    actions = [
        {
            "_index": index_name,
            "_id": doc["id"],
            "_source": {**doc, "text_vector": vector.tolist()},
        }
        for doc, vector in zip(docs, vectors)
    ]
    bulk(es, actions)
    es.indices.refresh(index=index_name)
    return len(actions)


def search_text(es: Elasticsearch, query: str, index_name: str = ELASTIC_INDEX_NAME, num_results: int = 5) -> list[dict]:
    body = {
        "size": num_results,
        "query": {"multi_match": {"query": query, "fields": ["title^2", "abstract", "authors"]}},
    }
    resp = es.search(index=index_name, body=body)
    return [{**hit["_source"], "_score": hit["_score"]} for hit in resp["hits"]["hits"]]


def search_knn(es: Elasticsearch, query: str, index_name: str = ELASTIC_INDEX_NAME, num_results: int = 5) -> list[dict]:
    query_vector = embed_query(query).tolist()
    body = {
        "size": num_results,
        "knn": {
            "field": "text_vector",
            "query_vector": query_vector,
            "k": num_results,
            "num_candidates": max(50, num_results * 10),
        },
    }
    resp = es.search(index=index_name, body=body)
    return [{**hit["_source"], "_score": hit["_score"]} for hit in resp["hits"]["hits"]]


def _reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


def search_hybrid(
    es: Elasticsearch,
    query: str,
    index_name: str = ELASTIC_INDEX_NAME,
    num_results: int = 5,
    candidate_pool: int = 20,
) -> list[dict]:
    text_hits = search_text(es, query, index_name, num_results=candidate_pool)
    knn_hits = search_knn(es, query, index_name, num_results=candidate_pool)

    by_id = {hit["id"]: hit for hit in text_hits + knn_hits}
    fused = _reciprocal_rank_fusion([[h["id"] for h in text_hits], [h["id"] for h in knn_hits]])
    ranked_ids = sorted(fused, key=lambda doc_id: fused[doc_id], reverse=True)[:num_results]

    return [{**by_id[doc_id], "_rrf_score": fused[doc_id]} for doc_id in ranked_ids]
