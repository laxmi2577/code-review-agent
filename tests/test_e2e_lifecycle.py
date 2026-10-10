import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import faiss
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.core.ast_parser import ASTParser
from src.core.diff_parser import map_diff_to_functions, parse_unified_diff
from src.core.retriever import CodeRetriever
from src.core.reviewer import GeminiReviewer
from src.main import create_app
from src.models.enums import ChangeType, Language, ReviewSeverity
from src.models.schemas import (
    DiffHunk,
    FunctionNode,
)
from src.services.github_client import GitHubClient
from src.services.incremental_indexer import IncrementalIndexer
from src.services.index_manager import IndexManager
from src.services.storage_client import StorageClient


@pytest.fixture
def e2e_environment(tmp_path: Path):
    """Set up an isolated end-to-end testing environment."""
    indices_dir = tmp_path / "indices"
    indices_dir.mkdir(parents=True, exist_ok=True)
    feedback_file = tmp_path / "feedback" / "reactions.jsonl"
    feedback_file.parent.mkdir(parents=True, exist_ok=True)

    dim = 4
    idx = faiss.IndexFlatIP(dim)
    # Seed index with 2 codebase functions
    v0 = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    idx.add(v0)

    nodes = [
        {
            "embedding_id": "0",
            "file_path": "src/auth.py",
            "function_name": "verify_jwt_token",
            "language": "python",
            "start_line": 10,
            "end_line": 25,
            "code_snippet": "def verify_jwt_token(token: str) -> bool:\n    return len(token) > 0\n",
        },
        {
            "embedding_id": "1",
            "file_path": "src/database.py",
            "function_name": "get_db_session",
            "language": "python",
            "start_line": 5,
            "end_line": 15,
            "code_snippet": "def get_db_session():\n    yield None\n",
        },
    ]

    metadata = {
        "repo_name": "org/repo",
        "dimension": dim,
        "nodes": nodes,
    }

    idx_path = indices_dir / "faiss_index.bin"
    meta_path = indices_dir / "metadata.json"
    faiss.write_index(idx, str(idx_path))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    secret = "e2e-webhook-secret-key"
    settings = Settings(
        _env_file=None,
        target_repo="org/repo",
        github_webhook_secret=secret,
        github_token="ghp_test_token",
        gemini_api_key="mock_gemini_key",
        local_index_path=str(idx_path),
        local_metadata_path=str(meta_path),
        feedback_store_path=str(feedback_file),
    )

    storage = StorageClient(settings=settings, base_cache_dir=tmp_path)
    index_mgr = IndexManager(settings=settings, storage_client=storage)
    index_mgr.load_index(index_path=idx_path, metadata_path=meta_path)

    return {
        "tmp_path": tmp_path,
        "settings": settings,
        "storage": storage,
        "index_mgr": index_mgr,
        "secret": secret,
        "feedback_file": feedback_file,
    }


def test_full_pr_lifecycle_simulation(e2e_environment):
    """Simulate complete PR lifecycle:
    1. Diff extraction
    2. AST parsing & Diff-to-AST mapping
    3. Context retrieval
    4. Gemini review generation
    5. GitHub inline comments posting
    6. Developer reaction feedback ingestion
    7. Post-merge incremental vector indexing
    """
    env = e2e_environment
    settings = env["settings"]
    index_mgr = env["index_mgr"]
    feedback_file = env["feedback_file"]

    # 1. Realistic Unified Diff for a PR modifying auth.py
    pr_unified_diff = """diff --git a/src/auth.py b/src/auth.py
index 1111111..2222222 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,6 +10,10 @@ def verify_jwt_token(token: str) -> bool:
+    # Insecure fallback added by junior dev
+    if token == "admin":
+        return True
     return len(token) > 0
"""

    # Parse diff hunks
    hunks = parse_unified_diff(pr_unified_diff)
    assert len(hunks) == 1
    hunk = hunks[0]
    assert hunk.file_path == "src/auth.py"
    assert hunk.new_start == 10

    # 2. AST parsing & Diff-to-AST mapping
    py_source = (
        "# Header imports\n"
        "# Line 2\n# Line 3\n# Line 4\n# Line 5\n# Line 6\n# Line 7\n# Line 8\n# Line 9\n"
        "def verify_jwt_token(token: str) -> bool:\n"
        '    if token == "admin":\n'
        "        return True\n"
        "    return len(token) > 0\n"
    )
    ast_parser = ASTParser()
    func_nodes = ast_parser.parse_source(
        code=py_source, file_path="src/auth.py", language=Language.PYTHON
    )
    assert len(func_nodes) == 1
    assert func_nodes[0].function_name == "verify_jwt_token"
    assert func_nodes[0].start_line == 10

    mapped_hunks = map_diff_to_functions(hunks, {"src/auth.py": func_nodes})
    assert len(mapped_hunks[0].affected_functions) == 1
    assert mapped_hunks[0].affected_functions[0].function_name == "verify_jwt_token"

    # 3. Context Retrieval
    retriever = CodeRetriever(index_manager=index_mgr)
    query_func = func_nodes[0]
    # Query vector matching seed function 0 in index
    query_vector = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    seed_func = FunctionNode(
        file_path="src/security.py",
        function_name="verify_jwt_token",
        language=Language.PYTHON,
        start_line=10,
        end_line=25,
        code_snippet="def verify_jwt_token...",
    )
    with patch.object(index_mgr, "query", return_value=([seed_func], [0.98])):
        retrieval_res = retriever.retrieve_similar(
            query_function=query_func,
            query_embedding=query_vector,
            exclude_self=False,
        )

    assert len(retrieval_res.similar_functions) == 1
    assert retrieval_res.similar_functions[0].function_name == "verify_jwt_token"

    # 4. Review Generation with GeminiReviewer
    reviewer = GeminiReviewer(settings=settings)
    mock_gemini_json = json.dumps(
        [
            {
                "file_path": "src/auth.py",
                "start_line": 10,
                "end_line": 14,
                "body": "Hardcoded 'admin' token bypasses cryptographic signature verification. Potential critical vulnerability.",
                "severity": "critical",
            }
        ]
    )

    with patch("google.generativeai.GenerativeModel") as mock_model_cls:
        mock_instance = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = mock_gemini_json
        mock_instance.generate_content.return_value = mock_resp
        mock_model_cls.return_value = mock_instance

        review_comments = reviewer.generate_review(
            diff_hunks=mapped_hunks,
            retrieval_results=[retrieval_res],
        )

    assert len(review_comments) == 1
    comment = review_comments[0]
    assert comment.severity == ReviewSeverity.CRITICAL
    assert "Hardcoded 'admin' token" in comment.body

    # 5. Post comments to GitHub PR via GitHubClient
    with patch("src.services.github_client.Github") as mock_gh_cls:
        mock_gh = MagicMock()
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_commit = MagicMock()

        mock_gh_cls.return_value = mock_gh
        mock_gh.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_commit.return_value = mock_commit

        mock_comment_obj = MagicMock()
        mock_comment_obj.id = 12345
        mock_pr.create_review_comment.return_value = mock_comment_obj

        client = GitHubClient(settings=settings)
        posted_ids = client.post_review_comments(
            repo_full_name="org/repo",
            pr_number=42,
            commit_id="2222222",
            comments=review_comments,
        )
        assert len(posted_ids) == 1
        assert mock_pr.create_review_comment.call_count == 1

    # 6. Webhook and Feedback Endpoints via FastAPI TestClient
    with (
        patch("src.api.feedback.get_settings", return_value=settings),
        patch("src.config.get_settings", return_value=settings),
    ):
        app = create_app()
        test_client = TestClient(app)

        # Ingest engineer reaction: +1 (helpful critical finding)
        fb_payload = {
            "pr_number": 42,
            "comment_id": "cmt_9988",
            "repo_full_name": "org/repo",
            "reaction": "+1",
            "timestamp": "2026-10-10T12:00:00Z",
        }
        fb_resp = test_client.post("/feedback", json=fb_payload)
        assert fb_resp.status_code == 200
        assert fb_resp.json()["status"] == "recorded"

        # Verify appended to reactions.jsonl
        assert feedback_file.exists()
        lines = feedback_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        stored = json.loads(lines[0])
        assert stored["reaction"] == "+1"
        assert stored["pr_number"] == 42

    # 7. Post-Merge Incremental Indexing
    new_func = FunctionNode(
        file_path="src/auth.py",
        function_name="verify_jwt_token_v2",
        language=Language.PYTHON,
        start_line=30,
        end_line=40,
        code_snippet="def verify_jwt_token_v2(): pass",
    )
    new_hunk = DiffHunk(
        file_path="src/auth.py",
        language=Language.PYTHON,
        change_type=ChangeType.ADDED,
        old_start=0,
        new_start=30,
        new_end=40,
        diff_content="+def verify_jwt_token_v2(): pass\n",
        affected_functions=[new_func],
    )

    dummy_embedder = lambda texts: np.full((len(texts), 4), 0.5, dtype=np.float32)
    incremental_indexer = IncrementalIndexer(
        index_manager=index_mgr,
        storage_client=env["storage"],
        settings=settings,
    )

    updated_count = incremental_indexer.update_for_diff_hunks(
        diff_hunks=[new_hunk],
        embed_fn=dummy_embedder,
        repo_name="org/repo",
    )
    assert updated_count == 1
    assert index_mgr.total_vectors == 3  # grew from 2 to 3 vectors
