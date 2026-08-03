"""Two prompt variants for the final-answer step, compared in the LLM evaluation
(eval/evaluate_rag.py) so we can pick the best one rather than evaluating just one."""

STRICT_PROMPT = """
You are a research assistant answering questions about retrieval-augmented generation,
LLM agents, and related NLP/ML topics, using ONLY the CONTEXT below (arXiv paper
abstracts). Do not use outside knowledge. If the CONTEXT does not contain enough
information to answer, say so plainly instead of guessing. Cite papers by their arXiv
id in square brackets, e.g. [2312.10997], for every claim you make.

QUESTION: {question}

CONTEXT:
{context}
""".strip()

CONCISE_PROMPT = """
Using the paper abstracts in CONTEXT, give a short, direct answer to QUESTION.
Mention the most relevant paper title(s) inline. If CONTEXT doesn't cover the
question, say so briefly.

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
        f"[{d['id']}] {d['title']}\nAuthors: {d.get('authors', '')}\nAbstract: {d['abstract']}"
        for d in docs
    )


def build_prompt(question: str, docs: list[dict], variant: str = "strict") -> str:
    template = PROMPT_VARIANTS[variant]
    return template.format(question=question, context=build_context(docs))
