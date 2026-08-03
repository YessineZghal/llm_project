"""Agentic RAG variant (project.md's "combination of RAG and agent" option): a tool-calling
loop (toyaikit) that can search our indexed knowledge base and, when that's not enough,
search arXiv live for papers outside the curated set.
"""

from toyaikit.chat.runners import OpenAIChatCompletionsRunner
from toyaikit.llm import OpenAIChatCompletionsClient
from toyaikit.tools import Tools

from llm_project.config import OPENAI_CHAT_MODEL
from llm_project.ingest.arxiv_source import fetch_topic
from llm_project.search.retriever import retrieve

DEVELOPER_PROMPT = """
You are a research assistant specialized in retrieval-augmented generation, LLM agents,
and related NLP/ML topics.

You have two tools:
- search_knowledge_base: search a curated, indexed set of arXiv paper abstracts. Always
  try this first.
- search_arxiv_live: search arXiv directly for papers NOT in the curated knowledge base
  (e.g. very recent papers, or topics outside the curated set). Only use this if the
  knowledge base doesn't return enough relevant information.

Always cite papers by their arXiv id in square brackets, e.g. [2312.10997]. If neither
tool returns relevant information, say so plainly instead of guessing.
""".strip()


def search_knowledge_base(query: str) -> list[dict]:
    """Search the curated, indexed knowledge base of arXiv paper abstracts on RAG,
    LLM agents, and related NLP/ML topics.

    Args:
        query: search query describing what to look for
    """
    docs = retrieve(query, method="es_hybrid_rerank", num_results=5)
    return [
        {"id": d["id"], "title": d["title"], "abstract": d["abstract"], "url": d.get("url", "")}
        for d in docs
    ]


def search_arxiv_live(topic: str) -> list[dict]:
    """Search arXiv directly (live, not from the curated knowledge base) for papers on a topic.

    Args:
        topic: topic to search for on arXiv
    """
    papers = fetch_topic(topic, max_results=5)
    return [
        {"id": p["id"], "title": p["title"], "abstract": p["abstract"][:500], "url": p["url"]}
        for p in papers
    ]


def build_agent_runner() -> OpenAIChatCompletionsRunner:
    tools = Tools()
    tools.add_tool(search_knowledge_base)
    tools.add_tool(search_arxiv_live)
    llm_client = OpenAIChatCompletionsClient(model=OPENAI_CHAT_MODEL)
    return OpenAIChatCompletionsRunner(
        tools=tools,
        developer_prompt=DEVELOPER_PROMPT,
        llm_client=llm_client,
    )


def ask_agent(question: str, previous_messages: list | None = None):
    runner = build_agent_runner()
    return runner.loop(question, previous_messages=previous_messages)
