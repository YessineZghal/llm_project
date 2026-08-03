"""Generate the retrieval evaluation ground truth (plan.md Step 8): a
stratified question set covering every document type in the corpus, plus a
hand-curated set of genuinely unanswerable questions - things the corpus
should not be able to answer, used to check the system doesn't confidently
retrieve a false match for out-of-scope questions.

Target distribution (plan.md Step 8): 25 provider-profile, 20 test-definition,
20 metric-definition, 20 methodology, 20 comparison-support, 15 unanswerable.
"""

import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
from tqdm import tqdm

from llm_project.config import GROUND_TRUTH_PATH, OPENAI_API_KEY, OPENAI_CHAT_MODEL
from llm_project.search.load_docs import load_docs

GENERATION_PROMPT = """
You are building a retrieval test set for an NHS diagnostic waiting-time application.

Given the document below, write {n} short, natural-language question(s) a user of the
application might ask that this document answers well. Questions must be answerable
from the document alone, must NOT quote the title verbatim, and must sound like a real
question a hospital operations analyst or member of the public would type.

Document type: {document_type}
Title: {title}
Content: {abstract}

Return a JSON object of the exact form {{"questions": ["...", "..."]}} with exactly
{n} items, nothing else.
""".strip()

# Hand-curated: questions the corpus should NOT be able to answer, either
# because they ask for something out of scope (individual patients, tests
# not covered, clinical advice) or reference data the corpus doesn't have.
UNANSWERABLE_QUESTIONS = [
    "Should I get an MRI sooner than the person ahead of me on the waiting list?",
    "What is my personal waiting time going to be for my knee scan?",
    "Which doctor will perform my colonoscopy?",
    "What is the waiting list for PET scans?",
    "What is the waiting list for X-ray appointments?",
    "How long will I personally wait for an ultrasound next month?",
    "Can you diagnose my symptoms based on my waiting list position?",
    "What is the waiting-time data for Wales or Scotland?",
    "What was the MRI waiting list in the year 2015?",
    "Which specific radiographer has the shortest average appointment time?",
    "What is the waiting list for a provider called 'St Nowhere Hospital'?",
    "Should this hospital hire more staff based on its bottleneck score?",
    "What insurance does a patient need for a covered diagnostic test?",
    "What is the exact cost of an MRI scan at this provider?",
    "Can I book an appointment through this application?",
]


def _generate_for_doc(doc: dict, client: OpenAI, n: int) -> list[str]:
    prompt = GENERATION_PROMPT.format(
        n=n, document_type=doc.get("document_type", "unknown"), title=doc["title"], abstract=doc["abstract"]
    )
    response = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content or "{}")
    return data.get("questions", [])[:n]


def _stratified_sample(docs: list[dict], document_type: str, k: int, rng: random.Random) -> list[dict]:
    pool = [d for d in docs if d["document_type"] == document_type]
    return rng.sample(pool, min(k, len(pool)))


def generate_ground_truth(seed: int = 42, max_workers: int = 8) -> list[dict]:
    docs = load_docs()
    rng = random.Random(seed)
    client = OpenAI(api_key=OPENAI_API_KEY)

    # (sample docs, questions-per-doc) chosen so each stratum lands close to
    # its plan.md Step 8 target count, given how many source docs exist.
    jobs: list[tuple[dict, int]] = []
    jobs += [(d, 1) for d in _stratified_sample(docs, "provider_profile", 25, rng)]
    jobs += [(d, 5) for d in _stratified_sample(docs, "test_definition", 4, rng)]  # 4 docs x 5 = 20
    jobs += [(d, 4) for d in _stratified_sample(docs, "metric_definition", 5, rng)]  # 5 docs x 4 = 20
    jobs += [(d, 5) for d in _stratified_sample(docs, "methodology", 4, rng)]  # 4 docs x 5 = 20

    # comparison-support: a distinct sample of provider profiles (not overlapping
    # the 25 above), phrased as single-fact lookups useful for comparing providers.
    used_ids = {d["id"] for d, _ in jobs if d["document_type"] == "provider_profile"}
    comparison_pool = [d for d in docs if d["document_type"] == "provider_profile" and d["id"] not in used_ids]
    comparison_docs = rng.sample(comparison_pool, min(20, len(comparison_pool)))
    jobs += [(d, 1) for d in comparison_docs]
    comparison_doc_ids = {d["id"] for d in comparison_docs}

    rows: list[dict] = []
    qid = 1
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_generate_for_doc, doc, client, n): (doc, n) for doc, n in jobs}
        for future in tqdm(as_completed(futures), total=len(futures), desc="generating ground truth"):
            doc, _ = futures[future]
            questions = future.result()
            for q in questions:
                doc_type = "comparison_support" if doc["id"] in comparison_doc_ids else doc["document_type"]
                rows.append(
                    {
                        "question_id": f"q{qid:03d}",
                        "question": q,
                        "relevant_document_ids": [doc["id"]],
                        "document_type": doc_type,
                        "answerable": True,
                    }
                )
                qid += 1

    for q in UNANSWERABLE_QUESTIONS:
        rows.append(
            {
                "question_id": f"q{qid:03d}",
                "question": q,
                "relevant_document_ids": [],
                "document_type": "unanswerable",
                "answerable": False,
            }
        )
        qid += 1

    GROUND_TRUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GROUND_TRUTH_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    return rows


if __name__ == "__main__":
    rows = generate_ground_truth()
    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r["document_type"]] = by_type.get(r["document_type"], 0) + 1
    print(f"Generated {len(rows)} ground-truth questions -> {GROUND_TRUTH_PATH}")
    for doc_type, count in sorted(by_type.items()):
        print(f"  {doc_type}: {count}")
