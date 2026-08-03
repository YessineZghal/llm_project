import time

import streamlit as st

from llm_project.config import OPENAI_CHAT_MODEL
from llm_project.db.client import log_conversation, log_feedback
from llm_project.rag.agent import ask_agent
from llm_project.rag.pipeline import answer_question
from llm_project.search.retriever import METHODS

st.set_page_config(page_title="LLM/RAG/Agents Research Assistant", page_icon="📚", layout="wide")


@st.cache_resource(show_spinner="Loading embedding + reranking models...")
def warm_up_models():
    from llm_project.search.embeddings import get_embedder
    from llm_project.search.rerank import get_reranker

    get_embedder()
    get_reranker()
    return True


warm_up_models()

if "messages" not in st.session_state:
    st.session_state.messages = []  # each: {role, content, conv_id, sources, voted}
if "agent_history" not in st.session_state:
    st.session_state.agent_history = []

with st.sidebar:
    st.header("Settings")
    mode = st.radio("Mode", ["RAG", "Agent (RAG + tools)"], index=0)
    if mode == "RAG":
        retrieval_method = st.selectbox("Retrieval method", METHODS, index=METHODS.index("es_hybrid_rerank"))
        prompt_variant = st.selectbox("Prompt variant", ["strict", "concise"], index=0)
        num_results = st.slider("Number of retrieved papers", 1, 10, 5)
        rewrite = st.checkbox("Rewrite query before retrieval", value=True)
    st.divider()
    st.caption(f"Model: `{OPENAI_CHAT_MODEL}`")
    st.caption("Knowledge base: ~400 arXiv abstracts on RAG, LLM agents & evaluation.")
    if st.button("Clear chat"):
        st.session_state.messages = []
        st.session_state.agent_history = []
        st.rerun()

st.title("📚 LLM / RAG / Agents Research Assistant")
st.caption(
    "Ask questions about retrieval-augmented generation, LLM agents, and related NLP/ML research. "
    "Answers are grounded in a curated set of arXiv paper abstracts."
)

for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            if message.get("sources"):
                with st.expander(f"Sources ({len(message['sources'])})"):
                    for doc in message["sources"]:
                        st.markdown(
                            f"**[{doc.get('id', '')}] {doc.get('title', '')}**  \n"
                            f"[{doc.get('url', '')}]({doc.get('url', '')})"
                        )
            if message.get("elapsed") is not None:
                st.caption(f"Answered in {message['elapsed']:.1f}s")
            if message.get("conv_id"):
                col1, col2, _ = st.columns([1, 1, 10])
                voted = message.get("voted")
                with col1:
                    if st.button("👍", key=f"up_{i}", disabled=voted is not None):
                        log_feedback(message["conv_id"], 1)
                        message["voted"] = "up"
                        st.rerun()
                with col2:
                    if st.button("👎", key=f"down_{i}", disabled=voted is not None):
                        log_feedback(message["conv_id"], -1)
                        message["voted"] = "down"
                        st.rerun()
                if voted:
                    st.caption(f"Thanks for the feedback ({'👍' if voted == 'up' else '👎'})")

question = st.chat_input("Ask about RAG, LLM agents, evaluation...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            start = time.time()

            if mode == "RAG":
                result = answer_question(
                    question,
                    method=retrieval_method,
                    num_results=num_results,
                    rewrite=rewrite,
                    prompt_variant=prompt_variant,
                )
                elapsed = time.time() - start
                answer = result["answer"]
                sources = result["docs"]

                conv_id = None
                try:
                    conv_id = log_conversation(
                        question=question,
                        answer=answer,
                        mode="rag",
                        model=OPENAI_CHAT_MODEL,
                        response_time_seconds=elapsed,
                        search_query=result["search_query"],
                        retrieval_method=retrieval_method,
                        prompt_variant=prompt_variant,
                        source_doc_ids=[d["id"] for d in sources],
                    )
                except Exception as e:
                    st.caption(f"(monitoring DB unavailable: {e})")

            else:
                loop_result = ask_agent(question, previous_messages=st.session_state.agent_history or None)
                elapsed = time.time() - start
                answer = loop_result.last_message
                st.session_state.agent_history = loop_result.all_messages

                sources = []
                for m in loop_result.new_messages:
                    role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
                    if role == "tool":
                        import json as _json

                        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
                        try:
                            parsed = _json.loads(content)
                        except Exception:
                            parsed = None
                        if isinstance(parsed, list):
                            sources.extend(doc for doc in parsed if isinstance(doc, dict))

                conv_id = None
                try:
                    conv_id = log_conversation(
                        question=question,
                        answer=answer,
                        mode="agent",
                        model=OPENAI_CHAT_MODEL,
                        response_time_seconds=elapsed,
                        source_doc_ids=[d.get("id", "") for d in sources],
                    )
                except Exception as e:
                    st.caption(f"(monitoring DB unavailable: {e})")

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "conv_id": conv_id,
            "sources": sources,
            "voted": None,
            "elapsed": elapsed,
        }
    )
    st.rerun()
