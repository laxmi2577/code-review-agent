import json
from pathlib import Path

import faiss
import numpy as np
import pytest

from src.core.retriever import CodeRetriever
from src.models.enums import ChangeType, Language
from src.models.schemas import DiffHunk, FunctionNode, RetrievalResult
from src.services.index_manager import IndexManager


@pytest.fixture
def sample_faiss_setup(tmp_path: Path):
    """Create a temporary FAISS index (dimension 4) and metadata with 3 functions."""
    dim = 4
    index = faiss.IndexFlatIP(dim)

    # 3 normalized vectors
    v0 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    v1 = np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32)

    vectors = np.vstack([v0, v1, v2])
    index.add(vectors)

    nodes = [
        {
            "embedding_id": "0",
            "file_path": "src/auth.py",
            "function_name": "login_user",
            "class_name": None,
            "language": "python",
            "start_line": 10,
            "end_line": 25,
            "code_snippet": "def login_user(username, password): pass",
        },
        {
            "embedding_id": "1",
            "file_path": "src/auth.py",
            "function_name": "authenticate_token",
            "class_name": None,
            "language": "python",
            "start_line": 30,
            "end_line": 45,
            "code_snippet": "def authenticate_token(token): pass",
        },
        {
            "embedding_id": "2",
            "file_path": "src/db.py",
            "function_name": "connect_database",
            "class_name": None,
            "language": "python",
            "start_line": 5,
            "end_line": 15,
            "code_snippet": "def connect_database(dsn): pass",
        },
    ]

    metadata = {
        "repo_name": "org/repo",
        "dimension": dim,
        "nodes": nodes,
    }

    index_file = tmp_path / "faiss_index.bin"
    metadata_file = tmp_path / "metadata.json"

    faiss.write_index(index, str(index_file))
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    return index_file, metadata_file, nodes


def test_index_manager_unloaded():
    manager = IndexManager()
    assert not manager.is_loaded
    assert manager.total_vectors == 0
    assert manager.dimension == 0

    nodes, scores = manager.query(np.array([1.0, 0.0], dtype=np.float32))
    assert nodes == []
    assert scores == []


def test_index_manager_load_and_query(sample_faiss_setup):
    index_file, metadata_file, _ = sample_faiss_setup
    manager = IndexManager()

    success = manager.load_index(index_path=index_file, metadata_path=metadata_file)
    assert success is True
    assert manager.is_loaded is True
    assert manager.dimension == 4
    assert manager.total_vectors == 3

    # Query with vector identical to v0
    query_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    nodes, scores = manager.query(query_vec, top_k=2)

    assert len(nodes) == 2
    assert nodes[0].function_name == "login_user"
    assert nodes[1].function_name == "authenticate_token"
    assert scores[0] >= scores[1]


def test_retriever_query_with_self_exclusion(sample_faiss_setup):
    index_file, metadata_file, nodes_data = sample_faiss_setup
    manager = IndexManager()
    manager.load_index(index_path=index_file, metadata_path=metadata_file)

    retriever = CodeRetriever(index_manager=manager)

    query_func = FunctionNode.model_validate(nodes_data[0])
    result: RetrievalResult = retriever.retrieve_similar(query_func, top_k=1, exclude_self=True)

    assert isinstance(result, RetrievalResult)
    assert result.query_function.function_name == "login_user"
    assert len(result.similar_functions) == 1
    # Node 0 was excluded, so closest neighbor is Node 1
    assert result.similar_functions[0].function_name == "authenticate_token"
    assert len(result.similarity_scores) == 1


def test_retriever_unloaded_index():
    manager = IndexManager()
    retriever = CodeRetriever(index_manager=manager)

    dummy_func = FunctionNode(
        file_path="foo.py",
        function_name="bar",
        language=Language.PYTHON,
        start_line=1,
        end_line=5,
        code_snippet="def bar(): pass",
        embedding_id="0",
    )

    result = retriever.retrieve_similar(dummy_func)
    assert result.similar_functions == []
    assert result.similarity_scores == []


def test_retriever_for_hunks(sample_faiss_setup):
    index_file, metadata_file, nodes_data = sample_faiss_setup
    manager = IndexManager()
    manager.load_index(index_path=index_file, metadata_path=metadata_file)

    retriever = CodeRetriever(index_manager=manager)

    func = FunctionNode.model_validate(nodes_data[0])
    hunk = DiffHunk(
        file_path="src/auth.py",
        language=Language.PYTHON,
        change_type=ChangeType.MODIFIED,
        old_start=12,
        new_start=12,
        new_end=15,
        diff_content="@@ -12,2 +12,3 @@",
        affected_functions=[func],
    )

    results = retriever.retrieve_for_hunks([hunk], top_k=2)
    assert len(results) == 1
    assert results[0].query_function.function_name == "login_user"
