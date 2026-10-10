import json
import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src.config import get_settings
from src.core.ast_parser import ASTParser
from src.core.diff_parser import map_diff_to_functions, parse_unified_diff
from src.core.retriever import CodeRetriever
from src.core.reviewer import GeminiReviewer
from src.services.index_manager import IndexManager
from src.services.storage_client import StorageClient

st.set_page_config(
    page_title="CodeLens Admin & Intelligence Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom header CSS
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E88E5;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #757575;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #F8F9FA;
        border-radius: 8px;
        padding: 16px;
        border: 1px solid #E0E0E0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-header">🔍 CodeLens Admin & Intelligence Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Retrieval-Augmented Code Review Control Plane & Feedback Telemetry</div>',
    unsafe_allow_html=True,
)

settings = get_settings()
storage_client = StorageClient(settings=settings)

# Cache index manager in session state
if "index_manager" not in st.session_state:
    mgr = IndexManager(settings=settings, storage_client=storage_client)
    mgr.load_index()
    st.session_state.index_manager = mgr

index_manager: IndexManager = st.session_state.index_manager

# Sidebar Configuration
st.sidebar.title("⚙️ Control Plane Settings")
st.sidebar.text(f"App Env: {settings.app_env}")
st.sidebar.text(f"Target Repo: {settings.target_repo}")
st.sidebar.text(f"Storage Bucket: {settings.gcs_bucket}")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Reload Index from Disk"):
    success = index_manager.load_index()
    if success:
        st.sidebar.success("Index reloaded successfully!")
    else:
        st.sidebar.warning("Index not found or failed to load.")

# Tabs
tab1, tab2, tab3 = st.tabs(["📊 Vector Index Health", "💬 Human Feedback Analytics", "🧪 Live PR Review Tester"])

# Tab 1: Vector Index Health
with tab1:
    st.subheader("Repository Vector Index Status")
    col1, col2, col3, col4 = st.columns(4)

    is_loaded = index_manager.is_loaded
    col1.metric("Index Status", "🟢 Loaded" if is_loaded else "🔴 Not Loaded")
    col2.metric("Total Indexed Vectors", f"{index_manager.total_vectors:,}")
    col3.metric("Vector Dimension", f"{index_manager.dimension}")

    index_file = Path(settings.local_index_path)
    age_str = "N/A"
    if index_file.exists():
        age_seconds = int(time.time() - index_file.stat().st_mtime)
        age_str = f"{age_seconds // 60} min ago" if age_seconds >= 60 else f"{age_seconds}s ago"
    col4.metric("Last Updated", age_str)

    st.markdown("### Storage Paths")
    st.code(f"Index File:    {settings.local_index_path}\nMetadata File: {settings.local_metadata_path}")

    if not is_loaded:
        st.info(
            "💡 **Notice**: No index is currently loaded. Run `colab/colab_indexer.ipynb` on Google Colab "
            "to generate `faiss_index.bin` and `metadata.json`, and place them in the `./data/indices/` folder."
        )

# Tab 2: Feedback Analytics
with tab2:
    st.subheader("Developer Reactions & Quality Telemetry")
    feedback_file = Path(settings.feedback_store_path)

    records = []
    if feedback_file.exists():
        try:
            with open(feedback_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
        except Exception as e:
            st.error(f"Error reading feedback file: {e}")

    if records:
        df = pd.DataFrame(records)
        total = len(df)
        pos = (df["reaction"] == "+1").sum()
        neg = (df["reaction"] == "-1").sum()
        rate = (pos / total * 100.0) if total > 0 else 0.0

        fcol1, fcol2, fcol3, fcol4 = st.columns(4)
        fcol1.metric("Total Feedback Events", str(total))
        fcol2.metric("Accepted (+1)", str(pos))
        fcol3.metric("Rejected (-1)", str(neg))
        fcol4.metric("Acceptance Rate", f"{rate:.1f}%")

        st.markdown("### Recent Feedback Events")
        st.dataframe(df.tail(20), use_container_width=True)
    else:
        st.info("No feedback events logged yet. Reactions from GitHub will appear here once submitted via `/feedback`.")

# Tab 3: Live Review Tester
with tab3:
    st.subheader("Manual Pull Request Review Runner")
    with st.form("manual_review_form"):
        r_col1, r_col2 = st.columns([3, 1])
        with r_col1:
            form_repo = st.text_input("Repository Full Name", value=settings.target_repo)
        with r_col2:
            form_pr = st.number_input("PR Number", value=1, min_value=1, step=1)

        sample_diff = (
            "diff --git a/src/auth.py b/src/auth.py\n"
            "--- a/src/auth.py\n"
            "+++ b/src/auth.py\n"
            "@@ -10,3 +10,4 @@ def login(user, password):\n"
            "+    if password == 'admin': return True\n"
        )
        form_diff = st.text_area("Unified Diff Content", value=sample_diff, height=180)
        submitted = st.form_submit_button("🚀 Run CodeLens Analysis")

    if submitted:
        with st.spinner("Analyzing diff and retrieving codebase context..."):
            start = time.perf_counter()
            hunks = parse_unified_diff(form_diff)

            ast_parser = ASTParser()
            funcs_by_file = {h.file_path: [] for h in hunks}
            hunks = map_diff_to_functions(hunks, funcs_by_file)

            retriever = CodeRetriever(index_manager=index_manager)
            retrieval_results = retriever.retrieve_for_hunks(hunks)

            reviewer = GeminiReviewer(settings=settings)
            comments = reviewer.generate_review(hunks, retrieval_results)
            elapsed = (time.perf_counter() - start) * 1000.0

            st.success(f"Analysis completed in {elapsed:.1f}ms — Generated {len(comments)} comments.")

            if comments:
                for c in comments:
                    with st.expander(f"[{c.severity.value.upper()}] {c.file_path} (Lines {c.start_line}–{c.end_line})"):
                        st.markdown(c.body)
                        if c.retrieved_context_refs:
                            st.caption(f"Context references: {', '.join(c.retrieved_context_refs)}")
            else:
                st.info("No issues detected in the submitted diff.")
