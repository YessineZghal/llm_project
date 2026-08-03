"""User query rewriting (best-practices criterion): turn a conversational question into
a keyword-rich search query before hitting the retrieval indices."""

from openai import OpenAI

from llm_project.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL

REWRITE_PROMPT = """
Rewrite the user's question into a concise, keyword-rich search query optimized for
retrieving relevant arXiv paper abstracts about LLMs, retrieval-augmented generation,
and agents. Keep it short (under 15 words). Return ONLY the rewritten query, nothing else.

User question: {question}
""".strip()


def rewrite_query(question: str, client: OpenAI | None = None) -> str:
    client = client or OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": REWRITE_PROMPT.format(question=question)}],
        temperature=0,
    )
    rewritten = (response.choices[0].message.content or "").strip()
    return rewritten or question
