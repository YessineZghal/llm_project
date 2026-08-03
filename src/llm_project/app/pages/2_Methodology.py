"""Methodology page (plan.md Step 15): data sources, definitions, the
bottleneck score formula, limitations, and real evaluation results - all
pulled from already-generated real content (the RAG corpus and the eval
result files), not written separately here, so it can't drift out of sync.
"""

import pandas as pd
import streamlit as st

from llm_project.config import RETRIEVAL_EVAL_RESULTS_PATH
from llm_project.search.load_docs import load_docs

st.set_page_config(page_title="Methodology - ScanFlow AI", layout="wide")

st.title("Methodology")
st.caption("How this application's data and figures are produced, and how each layer was evaluated.")

docs = load_docs()
by_type = {}
for d in docs:
    by_type.setdefault(d.get("document_type"), []).append(d)

st.subheader("Data sources")
for d in by_type.get("methodology", []):
    with st.expander(d["title"]):
        st.write(d["abstract"])

st.divider()

st.subheader("Diagnostic tests covered")
for d in sorted(by_type.get("test_definition", []), key=lambda x: x["title"]):
    with st.expander(d["title"]):
        st.write(d["abstract"])

st.divider()

st.subheader("Metric definitions")
for d in sorted(by_type.get("metric_definition", []), key=lambda x: x["title"]):
    with st.expander(d["title"]):
        st.write(d["abstract"])

st.divider()

st.subheader("Retrieval evaluation results")
st.caption(
    "Every retrieval method compared on the same ground-truth question set. "
    "The best-performing method is used by default throughout the application."
)
if RETRIEVAL_EVAL_RESULTS_PATH.exists():
    df = pd.read_csv(RETRIEVAL_EVAL_RESULTS_PATH)
    df = df.sort_values("mrr", ascending=False)
    st.dataframe(
        df[["method", "hit_rate", "mrr", "recall_at_5", "recall_at_10", "ndcg_at_5"]],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Retrieval evaluation has not been run yet.")

st.divider()

st.subheader("Limitations")
st.markdown(
    "- The reporting window currently loaded is a small number of recent months; "
    "year-over-year comparisons and long-run persistence counts are reported as "
    "unavailable, not approximated, when insufficient history exists.\n"
    "- Community Diagnostic Centre activity cannot currently be linked to a specific "
    "NHS provider, since the published source data does not include that mapping.\n"
    "- The bottleneck score is a project-specific indicator for relative comparison, "
    "not an official NHS metric or a clinically validated measure.\n"
    "- Figures may be revised by NHS England after publication; each ingested file is "
    "tracked by its own content hash, so a revision is treated as a new source version.\n"
    "- This application reports aggregate, provider-level statistics only. It does not "
    "provide clinical advice, diagnosis, or individual patient prioritization."
)
