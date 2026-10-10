import json
from pathlib import Path

import pytest

from src.config import Settings
from src.services.storage_client import StorageClient


@pytest.fixture
def temp_storage(tmp_path: Path) -> StorageClient:
    settings = Settings(
        local_index_path=str(tmp_path / "indices" / "faiss_index.bin"),
        local_metadata_path=str(tmp_path / "indices" / "metadata.json"),
        gcs_bucket="test-bucket",
    )
    return StorageClient(settings=settings, base_cache_dir=tmp_path / "indices")


def test_storage_paths_and_sanitization(temp_storage: StorageClient):
    idx_p, meta_p = temp_storage.get_local_paths("my-org/my-repo")
    assert "my-org__my-repo" in str(idx_p)
    assert idx_p.name == "faiss_index.bin"
    assert meta_p.name == "metadata.json"


def test_missing_index_returns_none(temp_storage: StorageClient):
    idx_p, meta_p = temp_storage.download_index("unindexed/repo")
    assert idx_p is None
    assert meta_p is None
    assert not temp_storage.index_exists("unindexed/repo")


def test_save_and_retrieve_local_index(temp_storage: StorageClient):
    repo = "test/repo"
    dummy_bytes = b"FAISS_BINARY_DUMMY_DATA"
    metadata = {
        "repo_name": repo,
        "dimension": 128,
        "nodes": [
            {
                "file_path": "src/app.py",
                "function_name": "run",
                "language": "python",
                "start_line": 1,
                "end_line": 5,
                "code_snippet": "def run(): pass",
            }
        ],
    }

    idx_path, meta_path = temp_storage.save_index_data(repo, dummy_bytes, metadata)
    assert idx_path.exists()
    assert meta_path.exists()
    assert temp_storage.index_exists(repo)

    # Load metadata
    loaded_meta = temp_storage.load_metadata(repo)
    assert loaded_meta is not None
    assert loaded_meta["repo_name"] == repo
    assert len(loaded_meta["nodes"]) == 1

    # Download index returns cached paths
    down_idx, down_meta = temp_storage.download_index(repo)
    assert down_idx == idx_path
    assert down_meta == meta_path


def test_upload_missing_files_fails(temp_storage: StorageClient, tmp_path: Path):
    non_existent = tmp_path / "nowhere.bin"
    success = temp_storage.upload_index("test/repo", non_existent, non_existent)
    assert success is False


def test_upload_existing_files(temp_storage: StorageClient, tmp_path: Path):
    src_idx = tmp_path / "source_faiss.bin"
    src_meta = tmp_path / "source_meta.json"
    src_idx.write_bytes(b"DATA")
    src_meta.write_text(json.dumps({"test": 123}), encoding="utf-8")

    success = temp_storage.upload_index("upload/repo", src_idx, src_meta)
    assert success is True
    assert temp_storage.index_exists("upload/repo")
