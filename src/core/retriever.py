import logging

import numpy as np

from src.models.schemas import DiffHunk, FunctionNode, RetrievalResult
from src.services.index_manager import IndexManager

logger = logging.getLogger("codelens.retriever")


class CodeRetriever:
    """Orchestrates code similarity retrieval against the indexed repository codebase."""

    def __init__(self, index_manager: IndexManager):
        self.index_manager = index_manager

    def retrieve_similar(
        self,
        query_function: FunctionNode,
        top_k: int = 5,
        query_embedding: np.ndarray | None = None,
        exclude_self: bool = True,
    ) -> RetrievalResult:
        """Retrieve the top-k most similar functions for a given query FunctionNode.

        If query_embedding is provided, it is queried directly.
        Otherwise, if query_function.embedding_id is present, attempts vector reconstruction
        from the index manager.

        Returns a RetrievalResult schema instance with matched nodes and similarity scores.
        """
        if not self.index_manager.is_loaded:
            logger.warning(
                "Retriever called but index is not loaded. Returning empty retrieval result for '%s'.",
                query_function.function_name,
            )
            return RetrievalResult(
                query_function=query_function,
                similar_functions=[],
                similarity_scores=[],
            )

        # Resolve vector
        vector: np.ndarray | None = query_embedding
        if vector is None and query_function.embedding_id is not None:
            emb_id_str = str(query_function.embedding_id)
            if emb_id_str.isdigit():
                vector = self.index_manager.reconstruct_vector(int(emb_id_str))

        if vector is None:
            logger.info(
                "No embedding available for query function '%s' (embedding_id=%s). Returning empty result.",
                query_function.function_name,
                query_function.embedding_id,
            )
            return RetrievalResult(
                query_function=query_function,
                similar_functions=[],
                similarity_scores=[],
            )

        # Query index (retrieve extra item if excluding self)
        fetch_k = top_k + 1 if exclude_self else top_k
        nodes, scores = self.index_manager.query(vector, top_k=fetch_k)

        filtered_nodes: list[FunctionNode] = []
        filtered_scores: list[float] = []

        for node, score in zip(nodes, scores):
            if exclude_self:
                # Check identity match
                is_self_by_emb = (
                    query_function.embedding_id is not None
                    and node.embedding_id == query_function.embedding_id
                )
                is_self_by_name = (
                    node.file_path == query_function.file_path
                    and node.function_name == query_function.function_name
                )
                if is_self_by_emb or is_self_by_name:
                    continue

            filtered_nodes.append(node)
            filtered_scores.append(score)

            if len(filtered_nodes) >= top_k:
                break

        return RetrievalResult(
            query_function=query_function,
            similar_functions=filtered_nodes,
            similarity_scores=filtered_scores,
        )

    def retrieve_for_hunks(
        self,
        diff_hunks: list[DiffHunk],
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Retrieve similar context functions for all affected functions across multiple DiffHunks."""
        results: list[RetrievalResult] = []
        seen_keys: set[tuple[str, str]] = set()

        for hunk in diff_hunks:
            for func_node in hunk.affected_functions:
                key = (func_node.file_path, func_node.function_name)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                res = self.retrieve_similar(func_node, top_k=top_k)
                results.append(res)

        return results
