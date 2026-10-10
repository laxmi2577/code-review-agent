import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional, Union

import faiss
import numpy as np

from src.config import Settings, get_settings
from src.core.ast_parser import ASTParser
from src.core.diff_parser import extract_diff_from_repo, map_diff_to_functions
from src.models.enums import ChangeType
from src.models.schemas import DiffHunk, FunctionNode
from src.services.index_manager import IndexManager
from src.services.storage_client import StorageClient

logger = logging.getLogger("codelens.incremental_indexer")


class IncrementalIndexer:
    """Incrementally updates vector index and metadata when files are added, modified, or removed."""

    def __init__(
        self,
        index_manager: IndexManager,
        storage_client: Optional[StorageClient] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.index_manager = index_manager
        self.storage_client = storage_client or StorageClient(settings=self.settings)

    def update_for_diff_hunks(
        self,
        diff_hunks: list[DiffHunk],
        embed_fn: Optional[Callable[[list[str]], np.ndarray]] = None,
        repo_name: Optional[str] = None,
    ) -> int:
        """Update index metadata and vector embeddings for all functions affected by diff hunks.

        Returns the number of functions successfully updated or added.
        """
        if not self.index_manager.is_loaded or self.index_manager.index is None:
            logger.warning("IncrementalIndexer invoked on uninitialized index.")
            return 0

        target_repo = repo_name or self.settings.target_repo
        updated_count = 0

        for hunk in diff_hunks:
            for func in hunk.affected_functions:
                # 1. Update metadata in memory
                current_nodes = self.index_manager.metadata.get("nodes", [])
                node_idx = None

                # Find if node already exists by file_path and function_name
                for idx, item in enumerate(current_nodes):
                    if isinstance(item, dict):
                        f_path = item.get("file_path")
                        f_name = item.get("function_name")
                    else:
                        f_path = item.file_path
                        f_name = item.function_name

                    if f_path == func.file_path and f_name == func.function_name:
                        node_idx = idx
                        break

                if hunk.change_type == ChangeType.DELETED:
                    if node_idx is not None:
                        logger.info("Marking deleted function: %s in %s", func.function_name, func.file_path)
                        if isinstance(current_nodes[node_idx], dict):
                            current_nodes[node_idx]["deleted"] = True
                        updated_count += 1
                    continue

                # For ADDED or MODIFIED:
                if node_idx is not None:
                    # Update existing record
                    if isinstance(current_nodes[node_idx], dict):
                        current_nodes[node_idx]["code_snippet"] = func.code_snippet
                        current_nodes[node_idx]["start_line"] = func.start_line
                        current_nodes[node_idx]["end_line"] = func.end_line
                    updated_count += 1
                else:
                    # Append new function node
                    new_idx = len(current_nodes)
                    func.embedding_id = str(new_idx)
                    current_nodes.append(func.model_dump())
                    node_idx = new_idx
                    updated_count += 1

                # 2. Vector embedding update
                if embed_fn is not None:
                    vec = embed_fn([func.code_snippet]).astype(np.float32)
                    if vec.ndim == 1:
                        vec = vec.reshape(1, -1)

                    if vec.shape[1] == self.index_manager.dimension:
                        self.index_manager.index.add(vec)
                        logger.debug("Added vector for function %s to FAISS index.", func.function_name)

        # 3. Persist updated index and metadata snapshot to local cache
        idx_p, meta_p = self.storage_client.get_local_paths(target_repo)
        idx_p.parent.mkdir(parents=True, exist_ok=True)

        try:
            faiss.write_index(self.index_manager.index, str(idx_p))
            with open(meta_p, "w", encoding="utf-8") as f:
                json.dump(self.index_manager.metadata, f, indent=2)
            logger.info("Successfully persisted incremental update (%d functions) to %s", updated_count, idx_p)
        except Exception as e:
            logger.error("Failed to persist incremental index snapshot: %s", e)

        return updated_count

    def sync_on_merge(
        self,
        repo_path: str,
        base_sha: str,
        head_sha: str,
        embed_fn: Optional[Callable[[list[str]], np.ndarray]] = None,
    ) -> int:
        """Extract merged commits diff and incrementally update codebase vector index."""
        hunks = extract_diff_from_repo(repo_path, base_sha, head_sha)
        if not hunks:
            return 0

        ast_parser = ASTParser()
        functions_by_file = {}
        for hunk in hunks:
            full_p = Path(repo_path) / hunk.file_path
            if full_p.exists():
                code = full_p.read_text(encoding="utf-8", errors="ignore")
                nodes = ast_parser.extract_function_nodes(code, hunk.file_path, hunk.language)
                functions_by_file[hunk.file_path] = nodes
            else:
                functions_by_file[hunk.file_path] = []

        hunks = map_diff_to_functions(hunks, functions_by_file)
        return self.update_for_diff_hunks(hunks, embed_fn=embed_fn)
