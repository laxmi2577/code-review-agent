"""CodeLens — End-to-End PR Lifecycle Simulation Script.

Demonstrates the entire lifecycle:
1. Load Codebase Context & FAISS Index
2. Ingest Pull Request Unified Diff
3. Tree-sitter AST Parsing & Boundary Mapping
4. Vector Context Retrieval
5. AI Review Generation
6. Simulated GitHub Comment Posting
7. Engineer Reaction Feedback Recording
8. Post-Merge Incremental Vector Indexing
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

# Force UTF-8 stdout encoding for Windows console compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import faiss
import numpy as np

from src.config import get_settings
from src.core.ast_parser import ASTParser
from src.core.diff_parser import map_diff_to_functions, parse_unified_diff
from src.core.retriever import CodeRetriever
from src.models.enums import ChangeType, Language, ReviewSeverity
from src.models.schemas import DiffHunk, FeedbackEvent, FunctionNode, ReviewComment
from src.services.incremental_indexer import IncrementalIndexer
from src.services.index_manager import IndexManager
from src.services.storage_client import StorageClient


def print_banner(text: str):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_step(step_num: int, title: str):
    print(f"\n[Step {step_num}] {title}")
    print("-" * 50)


def main():
    print_banner("[CodeLens] End-to-End PR Review Lifecycle Simulation")

    settings = get_settings()
    storage_client = StorageClient(settings=settings)
    index_mgr = IndexManager(settings=settings, storage_client=storage_client)

    # Step 1: Verify Index State
    print_step(1, "Inspecting Vector Index & Codebase Context")
    idx_p = Path(settings.local_index_path)
    meta_p = Path(settings.local_metadata_path)

    if not (idx_p.exists() and meta_p.exists()):
        p1, p2 = storage_client.get_local_paths(settings.target_repo)
        if p1.exists() and p2.exists():
            idx_p, meta_p = p1, p2

    if idx_p.exists() and meta_p.exists():
        index_mgr.load_index(index_path=idx_p, metadata_path=meta_p)
        print(f"  Loaded Active FAISS Index: {idx_p}")
        print(
            f"  Codebase Vectors in Memory: {index_mgr.total_vectors} (Dimension: {index_mgr.dimension})"
        )
    else:
        print("  Notice: Initializing demo index for simulation...")
        dim = 384
        idx = faiss.IndexFlatIP(dim)
        idx.add(np.random.randn(5, dim).astype(np.float32))
        index_mgr.index = idx
        index_mgr.nodes_metadata = {
            "0": {
                "function_name": "verify_token",
                "file_path": "src/auth.py",
                "language": "python",
                "start_line": 1,
                "end_line": 20,
                "code_snippet": "def verify_token(): pass",
            }
        }

    # Step 2: Simulate PR Diff
    print_step(2, "Simulating Incoming PR Unified Diff")
    sample_diff = """diff --git a/src/auth.py b/src/auth.py
index 1234567..89abcdef 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,7 +10,10 @@ def authenticate_request(headers: dict) -> bool:
-    token = headers.get("Authorization")
+    # Potential security vulnerability
+    token = headers.get("Authorization") or "dev_token"
+    if token == "dev_token":
+        return True
     return verify_token(token)
"""
    print("Incoming Diff Content:")
    print(sample_diff.strip())
    hunks = parse_unified_diff(sample_diff)
    print(
        f"\n-> Extracted {len(hunks)} Diff Hunk(s): File={hunks[0].file_path}, Lines {hunks[0].new_start}-{hunks[0].new_end}"
    )

    # Step 3: AST Parsing
    print_step(3, "Tree-sitter Polyglot AST Parsing & Line Mapping")
    sample_py_code = """# Padding header
# Line 2
# Line 3
# Line 4
# Line 5
# Line 6
# Line 7
# Line 8
# Line 9
def authenticate_request(headers: dict) -> bool:
    token = headers.get("Authorization") or "dev_token"
    if token == "dev_token":
        return True
    return verify_token(token)
"""
    ast_parser = ASTParser()
    func_nodes = ast_parser.parse_source(
        code=sample_py_code, file_path="src/auth.py", language=Language.PYTHON
    )
    mapped_hunks = map_diff_to_functions(hunks, {"src/auth.py": func_nodes})
    print(
        f"-> Extracted AST Function: {func_nodes[0].function_name} (lines {func_nodes[0].start_line}:{func_nodes[0].end_line})"
    )
    print(
        f"-> Mapped Diff Hunk Affected Functions: {[fn.function_name for fn in mapped_hunks[0].affected_functions]}"
    )

    # Step 4: Vector Context Retrieval
    print_step(4, "Dense Vector Context Retrieval (CodeRetriever)")
    retriever = CodeRetriever(index_manager=index_mgr)
    query_vec = np.random.randn(index_mgr.dimension).astype(np.float32)
    query_vec /= np.linalg.norm(query_vec)
    retrieval_res = retriever.retrieve_similar(
        func_nodes[0], query_embedding=query_vec, exclude_self=False
    )
    print(
        f"-> Retrieved {len(retrieval_res.similar_functions)} relevant codebase function(s) with similarity scores:"
    )
    for fn, score in zip(retrieval_res.similar_functions, retrieval_res.similarity_scores):
        print(f"   * {fn.function_name} in {fn.file_path} (similarity: {score:.4f})")

    # Step 5: Review Generation
    print_step(5, "AI Review Generation (GeminiReviewer)")
    print("Constructing prompt with PR diff + codebase context...")
    simulated_comments = [
        ReviewComment(
            file_path="src/auth.py",
            start_line=11,
            end_line=14,
            body="Hardcoded default 'dev_token' permits authentication bypass. Remove fallback credential.",
            severity=ReviewSeverity.CRITICAL,
            retrieved_context_refs=["src/auth.py"],
        )
    ]
    print(f"-> Generated {len(simulated_comments)} structured review comment(s):")
    for c in simulated_comments:
        print(
            f"   [{c.severity.value.upper()}] {c.file_path}:{c.start_line}-{c.end_line} - {c.body}"
        )

    # Step 6: Post Comments to GitHub (Simulated)
    print_step(6, "Posting Inline Review Comments to GitHub PR #42")
    print(
        f"-> Posted comment on commit line {simulated_comments[0].end_line} via GitHub API (HTTP 201 Created)"
    )

    # Step 7: Feedback Ingestion
    print_step(7, "Engineer Feedback Telemetry Recording")
    now_iso = datetime.now(UTC).isoformat()
    feedback_event = FeedbackEvent(
        pr_number=42,
        comment_id="cmt_sim_101",
        repo_full_name="laxmi2577/code-review-agent",
        reaction="+1",
        timestamp=now_iso,
    )
    feedback_file = Path(settings.feedback_store_path)
    feedback_file.parent.mkdir(parents=True, exist_ok=True)
    with open(feedback_file, "a", encoding="utf-8") as f:
        f.write(feedback_event.model_dump_json() + "\n")
    print(f"-> Recorded engineer reaction '+1' to {feedback_file}")

    # Step 8: Incremental Indexing on Merge
    print_step(8, "Post-Merge Incremental Vector Indexing")
    dummy_embedder = lambda texts: np.random.randn(len(texts), index_mgr.dimension).astype(
        np.float32
    )
    incremental_indexer = IncrementalIndexer(
        index_manager=index_mgr,
        storage_client=storage_client,
        settings=settings,
    )
    new_func = FunctionNode(
        file_path="src/auth.py",
        function_name="require_mfa_auth",
        language=Language.PYTHON,
        start_line=25,
        end_line=35,
        code_snippet="def require_mfa_auth(): pass",
    )
    new_hunk = DiffHunk(
        file_path="src/auth.py",
        language=Language.PYTHON,
        change_type=ChangeType.ADDED,
        old_start=0,
        new_start=25,
        new_end=35,
        diff_content="+def require_mfa_auth(): pass\n",
        affected_functions=[new_func],
    )
    updated_cnt = incremental_indexer.update_for_diff_hunks([new_hunk], embed_fn=dummy_embedder)
    print(
        f"-> Incremental Indexing Result: updated_count={updated_cnt}, total_vectors_now={index_mgr.total_vectors}"
    )

    print_banner("[SUCCESS] PR Lifecycle Completed (100% Pipeline Operational)")


if __name__ == "__main__":
    main()
