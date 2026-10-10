import json
from pathlib import Path

import faiss
import numpy as np
import pytest

from src.config import Settings
from src.models.enums import ChangeType, Language
from src.models.schemas import DiffHunk, FunctionNode
from src.services.incremental_indexer import IncrementalIndexer
from src.services.index_manager import IndexManager
from src.services.storage_client import StorageClient


@pytest.fixture
def indexer_setup(tmp_path: Path):
    dim = 4
    idx = faiss.IndexFlatIP(dim)
    v0 = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    idx.add(v0)

    nodes = [
        {
            "embedding_id": "0",
            "file_path": "src/utils.py",
            "function_name": "helper",
            "language": "python",
            "start_line": 1,
            "end_line": 5,
            "code_snippet": "def helper(): return 1",
        }
    ]

    metadata = {
        "repo_name": "test/repo",
        "dimension": dim,
        "nodes": nodes,
    }

    settings = Settings(
        _env_file=None,
        target_repo="test/repo",
        local_index_path=str(tmp_path / "faiss_index.bin"),
        local_metadata_path=str(tmp_path / "metadata.json"),
    )
    storage = StorageClient(settings=settings, base_cache_dir=tmp_path)
    idx_p, meta_p = storage.get_local_paths("test/repo")
    idx_p.parent.mkdir(parents=True, exist_ok=True)

    faiss.write_index(idx, str(idx_p))
    with open(meta_p, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    mgr = IndexManager(settings=settings, storage_client=storage)
    mgr.load_index(index_path=idx_p, metadata_path=meta_p)

    return mgr, storage, settings


def test_incremental_update_modified_function(indexer_setup):
    mgr, storage, settings = indexer_setup
    indexer = IncrementalIndexer(index_manager=mgr, storage_client=storage, settings=settings)

    modified_func = FunctionNode(
        file_path="src/utils.py",
        function_name="helper",
        language=Language.PYTHON,
        start_line=1,
        end_line=10,
        code_snippet="def helper(): return 2",
    )
    hunk = DiffHunk(
        file_path="src/utils.py",
        language=Language.PYTHON,
        change_type=ChangeType.MODIFIED,
        old_start=1,
        new_start=1,
        new_end=10,
        diff_content="@@ -1,5 +1,10 @@",
        affected_functions=[modified_func],
    )

    updated = indexer.update_for_diff_hunks([hunk], repo_name="test/repo")
    assert updated == 1
    assert mgr.metadata["nodes"][0]["code_snippet"] == "def helper(): return 2"
    assert mgr.metadata["nodes"][0]["end_line"] == 10


def test_incremental_update_new_function(indexer_setup):
    mgr, storage, settings = indexer_setup
    indexer = IncrementalIndexer(index_manager=mgr, storage_client=storage, settings=settings)

    new_func = FunctionNode(
        file_path="src/new_module.py",
        function_name="brand_new_feature",
        language=Language.PYTHON,
        start_line=1,
        end_line=6,
        code_snippet="def brand_new_feature(): pass",
    )
    hunk = DiffHunk(
        file_path="src/new_module.py",
        language=Language.PYTHON,
        change_type=ChangeType.ADDED,
        old_start=0,
        new_start=1,
        new_end=6,
        diff_content="@@ -0,0 +1,6 @@",
        affected_functions=[new_func],
    )

    def dummy_embedder(snippets):
        return np.array([[0.0, 1.0, 0.0, 0.0]], dtype=np.float32)

    initial_total = mgr.total_vectors
    updated = indexer.update_for_diff_hunks([hunk], embed_fn=dummy_embedder, repo_name="test/repo")
    assert updated == 1
    assert mgr.total_vectors == initial_total + 1
    assert len(mgr.metadata["nodes"]) == 2


def test_unloaded_index_returns_zero():
    unloaded_mgr = IndexManager()
    indexer = IncrementalIndexer(index_manager=unloaded_mgr)
    count = indexer.update_for_diff_hunks([])
    assert count == 0
