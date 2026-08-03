"""Plain (non-agentic) RAG pipeline: rewrite -> retrieve -> prompt -> generate.

This is the "combination of both" RAG half of the app (see rag/agent.py for the
tool-calling agent variant), and the thing being evaluated in eval/evaluate_rag.py.
"""

from openai import OpenAI

from llm_project.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL
from llm_project.rag.prompts import build_prompt
from llm_project.rag.query_rewrite import rewrite_query
from llm_project.search.retriever import retrieve


def answer_question(
    question: str,
    method: str = "es_hybrid_rerank",
    num_results: int = 5,
    rewrite: bool = True,
    prompt_variant: str = "strict",
    client: OpenAI | None = None,
) -> dict:
    client = client or OpenAI(api_key=OPENAI_API_KEY)

    search_query = rewrite_query(question, client=client) if rewrite else question
    docs = retrieve(search_query, method=method, num_results=num_results)
    prompt = build_prompt(question, docs, variant=prompt_variant)

    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    answer = (response.choices[0].message.content or "").strip()

    return {
        "question": question,
        "search_query": search_query,
        "answer": answer,
        "docs": docs,
        "method": method,
        "prompt_variant": prompt_variant,
    }
