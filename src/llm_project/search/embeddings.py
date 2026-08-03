"""Sentence-embedding helper, shared by minsearch's vector mode and Elasticsearch's kNN field."""

from functools import lru_cache

import numpy as np

from llm_project.config import DATA_DIR, EMBEDDING_MODEL_NAME

EMBEDDINGS_CACHE_PATH = DATA_DIR / "embeddings_cache.npz"


@lru_cache(maxsize=1)
def get_embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_texts(texts: list[str]) -> np.ndarray:
    model = get_embedder()
    return np.asarray(model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False))


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def doc_text(doc: dict) -> str:
    return f"{doc['title']} {doc['abstract']}"


def embed_docs_cached(docs: list[dict]) -> np.ndarray:
    """Embed docs, reusing a disk cache keyed by doc id order so repeated
    index builds (eval script, app startup, notebooks) don't recompute."""
    ids = [d["id"] for d in docs]

    if EMBEDDINGS_CACHE_PATH.exists():
        cached = np.load(EMBEDDINGS_CACHE_PATH, allow_pickle=True)
        if list(cached["ids"]) == ids:
            return cached["vectors"]

    vectors = embed_texts([doc_text(d) for d in docs])
    np.savez(EMBEDDINGS_CACHE_PATH, ids=np.array(ids, dtype=object), vectors=vectors)
    return vectors
