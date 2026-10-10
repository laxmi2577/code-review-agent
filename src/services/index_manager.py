import json
import logging
from pathlib import Path
from typing import Any, Optional, Union

import faiss
import numpy as np

from src.config import Settings, get_settings
from src.models.schemas import FunctionNode
from src.services.storage_client import StorageClient

logger = logging.getLogger("codelens.index_manager")


class IndexManager:
    """Manages the in-memory FAISS index lifecycle and metadata retrieval."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        storage_client: Optional[StorageClient] = None,
    ):
        self.settings = settings or get_settings()
        self.storage_client = storage_client or StorageClient(settings=self.settings)
        self.index: Optional[faiss.Index] = None
        self.metadata: Optional[dict[str, Any]] = None
        self._nodes_by_index: dict[int, FunctionNode] = {}
        self._nodes_by_embedding_id: dict[str, FunctionNode] = {}

    @property
    def is_loaded(self) -> bool:
        """Return True if FAISS index is loaded into memory and ready for queries."""
        return self.index is not None

    @property
    def total_vectors(self) -> int:
        """Return the number of indexed vectors in the active FAISS index."""
        if self.index is not None:
            return self.index.ntotal
        return 0

    @property
    def dimension(self) -> int:
        """Return the vector dimension of the active FAISS index."""
        if self.index is not None:
            return self.index.d
        return 0

    def load_index(
        self,
        index_path: Optional[Union[str, Path]] = None,
        metadata_path: Optional[Union[str, Path]] = None,
        repo_name: Optional[str] = None,
    ) -> bool:
        """Load FAISS index binary and metadata JSON into memory.

        If explicit paths are not provided, attempts download/cache resolution via StorageClient.
        Returns False and logs warning if files are missing or corrupted.
        """
        resolved_repo = repo_name or self.settings.target_repo

        if not index_path or not metadata_path:
            idx_p, meta_p = self.storage_client.download_index(resolved_repo)
            if not idx_p or not meta_p:
                logger.warning(
                    "Unable to load index for '%s': index snapshot not found.",
                    resolved_repo,
                )
                return False
            index_path = idx_p
            metadata_path = meta_p

        idx_file = Path(index_path)
        meta_file = Path(metadata_path)

        if not idx_file.exists() or not meta_file.exists():
            logger.warning(
                "Missing index or metadata files: index=%s, metadata=%s",
                idx_file,
                meta_file,
            )
            return False

        try:
            # Load FAISS index
            loaded_index = faiss.read_index(str(idx_file))

            # Load metadata JSON
            with open(meta_file, "r", encoding="utf-8") as f:
                loaded_metadata = json.load(f)

            # Build node lookup tables
            nodes_by_idx: dict[int, FunctionNode] = {}
            nodes_by_emb_id: dict[str, FunctionNode] = {}

            raw_nodes = loaded_metadata.get("nodes", [])
            if isinstance(raw_nodes, list):
                for idx, node_data in enumerate(raw_nodes):
                    node = FunctionNode.model_validate(node_data)
                    nodes_by_idx[idx] = node
                    if node.embedding_id:
                        nodes_by_emb_id[str(node.embedding_id)] = node
                    else:
                        nodes_by_emb_id[str(idx)] = node
            elif isinstance(raw_nodes, dict):
                for k, node_data in raw_nodes.items():
                    node = FunctionNode.model_validate(node_data)
                    idx = int(k) if k.isdigit() else len(nodes_by_idx)
                    nodes_by_idx[idx] = node
                    if node.embedding_id:
                        nodes_by_emb_id[str(node.embedding_id)] = node
                    nodes_by_emb_id[str(k)] = node

            self.index = loaded_index
            self.metadata = loaded_metadata
            self._nodes_by_index = nodes_by_idx
            self._nodes_by_embedding_id = nodes_by_emb_id

            logger.info(
                "Loaded FAISS index with %d vectors (dimension: %d) and %d metadata nodes from %s",
                self.total_vectors,
                self.dimension,
                len(self._nodes_by_index),
                idx_file,
            )
            return True

        except Exception as e:
            logger.error("Failed to load FAISS index from %s: %s", idx_file, e, exc_info=True)
            self.index = None
            self.metadata = None
            self._nodes_by_index.clear()
            self._nodes_by_embedding_id.clear()
            return False

    def get_function_node(self, index_id: int) -> Optional[FunctionNode]:
        """Lookup FunctionNode by its vector row index in FAISS."""
        return self._nodes_by_index.get(index_id)

    def get_node_by_embedding_id(self, embedding_id: str) -> Optional[FunctionNode]:
        """Lookup FunctionNode by its string embedding_id."""
        return self._nodes_by_embedding_id.get(str(embedding_id))

    def reconstruct_vector(self, index_id: int) -> Optional[np.ndarray]:
        """Reconstruct the original embedding vector from FAISS if supported."""
        if self.index is None or index_id < 0 or index_id >= self.total_vectors:
            return None
        try:
            return self.index.reconstruct(index_id)
        except Exception as e:
            logger.warning("Could not reconstruct vector %d: %s", index_id, e)
            return None

    def query(
        self,
        embedding: np.ndarray,
        top_k: int = 5,
    ) -> tuple[list[FunctionNode], list[float]]:
        """Query FAISS index for nearest neighbors of the provided embedding.

        Returns a tuple of (matched_function_nodes, similarity_scores).
        """
        if not self.is_loaded or self.index is None or self.total_vectors == 0:
            logger.warning("Query executed against uninitialized or empty FAISS index.")
            return [], []

        # Prepare 2D float32 array
        vec = np.asarray(embedding, dtype=np.float32)
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)

        if vec.shape[1] != self.dimension:
            logger.error(
                "Query vector dimension mismatch: expected %d, got %d",
                self.dimension,
                vec.shape[1],
            )
            return [], []

        k = min(top_k, self.total_vectors)
        if k <= 0:
            return [], []

        distances, indices = self.index.search(vec, k)

        matched_nodes: list[FunctionNode] = []
        matched_scores: list[float] = []

        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue  # FAISS returns -1 for unfilled neighbor slots
            node = self.get_function_node(int(idx))
            if node:
                matched_nodes.append(node)
                matched_scores.append(float(dist))

        return matched_nodes, matched_scores
