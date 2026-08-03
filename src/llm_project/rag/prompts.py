"""Two prompt variants for the final-answer step, compared in the LLM pipeline
evaluation (eval/evaluate_llm_pipelines.py) so we pick the best one rather
than evaluating just one. Used by the simpler baseline pipelines
(rag/pipeline.py); the full agent (rag/agent.py) has its own, richer prompt
since it also has tools, not just retrieved context.
"""

STRICT_PROMPT = """
You are ScanFlow AI, answering questions about NHS England diagnostic waiting-time
and activity data, using ONLY the CONTEXT below (documents about providers,
diagnostic tests, metrics, and methodology). Do not use outside knowledge and never
calculate or estimate a number yourself - only state a number if it appears in the
CONTEXT. If the CONTEXT does not contain enough information to answer, say so plainly
instead of guessing. Cite documents by their id in square brackets, e.g.
[profile-RJ1-MRI], for every claim you make. Never state or imply a causal
relationship; describe associations only. Refuse individual clinical requests
(personal wait-time prediction, diagnosis, treatment advice, prioritizing a specific
patient) and explain that this application reports aggregate, provider-level
statistics only.

QUESTION: {question}

CONTEXT:
{context}
""".strip()

CONCISE_PROMPT = """
Using the documents in CONTEXT, give a short, direct answer to QUESTION. Only state a
number if it appears in CONTEXT - never calculate one yourself. Mention the most
relevant document id(s) inline. If CONTEXT doesn't cover the question, say so briefly.
Refuse individual clinical requests (personal wait-time prediction, diagnosis,
treatment advice) and explain that this application reports aggregate,
provider-level statistics only.

QUESTION: {question}

CONTEXT:
{context}
""".strip()

PROMPT_VARIANTS = {
    "strict": STRICT_PROMPT,
    "concise": CONCISE_PROMPT,
}


def build_context(docs: list[dict]) -> str:
    return "\n\n".join(
        f"[{d['id']}] {d['title']}\nCategory: {d.get('categories', '')}\nContent: {d['abstract']}"
        for d in docs
    )


def build_prompt(question: str, docs: list[dict], variant: str = "strict") -> str:
    template = PROMPT_VARIANTS[variant]
    return template.format(question=question, context=build_context(docs))
