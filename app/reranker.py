"""
TASK 3 — ANN Retrieval + Reranking (app/reranker.py)

Takes hybrid retrieval candidate documents and reranks them using a local Cross-Encoder model.
Exports:
  - `DocumentReranker` class with `rerank(query, candidates, top_n)` method.
"""

import logging
from typing import List, Dict, Any

from sentence_transformers import CrossEncoder

logger = logging.getLogger("reranker")

# ── Constants ───────────────────────────────────────────────────
RERANK_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class DocumentReranker:
    """
    Reranks candidate documents using a local Cross-Encoder transformer.
    """

    def __init__(self):
        self.model = None
        self._initialized = False

    def ensure_initialized(self) -> None:
        """Lazy-initialize the Cross-Encoder model."""
        if self._initialized:
            return

        logger.info("Loading Cross-Encoder model: %s", RERANK_MODEL_NAME)
        self.model = CrossEncoder(RERANK_MODEL_NAME)
        self._initialized = True
        logger.info("Cross-Encoder reranker initialized successfully.")

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Rerank retrieval candidates for a query using cross-encoder scores.

        Args:
            query: The user's query string.
            candidates: List of candidate dicts from HybridRetriever.
            top_n: Number of final high-confidence candidates to return.

        Returns:
            List of top top_n candidates sorted by cross-encoder score descending,
            with 'rerank_score' float added to each dictionary.
        """
        if not candidates:
            return []

        self.ensure_initialized()
        query_stripped = query.strip()
        if not query_stripped:
            return []

        # 1. Create text pairs: (query, document_text)
        pairs = [(query_stripped, c["text"]) for c in candidates]

        # 2. Predict cross-encoder matching scores
        logger.info("Reranking %d candidates using Cross-Encoder...", len(candidates))
        scores = self.model.predict(pairs)

        # 3. Add rerank_score to each candidate
        reranked_list = []
        for candidate, score in zip(candidates, scores):
            # Create a shallow copy to avoid mutating inputs
            candidate_copy = dict(candidate)
            candidate_copy["rerank_score"] = float(score)
            reranked_list.append(candidate_copy)

        # 4. Sort by rerank_score descending
        reranked_list.sort(key=lambda x: x["rerank_score"], reverse=True)

        return reranked_list[:top_n]


# Singleton instance exported for use
reranker = DocumentReranker()
