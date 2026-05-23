"""
TASK 4 — Source Confidence Scoring (app/confidence.py)

Score each retrieved chunk for reliability before sending to the LLM.
Exports:
  - `ConfidenceScorer` class with `score_chunks(query, chunks)` method.
  - `confidence_scorer` (singleton instance of ConfidenceScorer).
"""

import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger("confidence")


class ConfidenceScorer:
    """
    Computes confidence scores for retrieved, reranked chunks based on
    freshness, source authority, lexical overlap, and retrieval consistency.
    """

    def tokenize(self, text: str) -> set:
        """
        Tokenize a string by converting to lowercase, removing punctuation,
        and splitting on whitespace. Returns a set of tokens.
        """
        if not text:
            return set()
        # Remove punctuation, convert to lowercase, and split
        clean_text = re.sub(r"[^\w\s]", " ", text.lower())
        return set(clean_text.split())

    def score_chunks(self, query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Score each chunk and filter out those below the threshold (0.35).

        Args:
            query: The user's query string.
            chunks: List of reranked candidate chunk dicts (from app/reranker.py).

        Returns:
            Filtered list of chunks, sorted by confidence_score descending,
            with 'confidence_score' float added to each chunk.
        """
        if not chunks:
            logger.info("No chunks provided to score.")
            return []

        logger.info("Scoring confidence for %d chunks...", len(chunks))

        # ── Step 1: Pre-calculate min and max rerank_scores for normalization ──
        scores = [c.get("rerank_score", 0.0) for c in chunks]
        min_s = min(scores)
        max_s = max(scores)
        score_range = max_s - min_s

        # Tokenize query once
        query_tokens = self.tokenize(query)

        scored_chunks = []

        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            
            # 1. Freshness score (weight = 0.2)
            # Parse ingested_at ISO timestamp.
            # E.g. '2026-05-22T18:05:06.123456+00:00'
            freshness = 0.4  # Default if missing or invalid
            ingested_at_str = metadata.get("ingested_at")
            if ingested_at_str:
                try:
                    # fromisoformat handles +00:00 timezone offset correctly
                    dt = datetime.fromisoformat(ingested_at_str)
                    now = datetime.now(timezone.utc)
                    days = (now - dt).days
                    if days <= 30:
                        freshness = 1.0
                    elif days <= 90:
                        freshness = 0.7
                    else:
                        freshness = 0.4
                except Exception as e:
                    logger.warning("Could not parse ingested_at '%s': %s", ingested_at_str, e)
            
            # 2. Authority score (weight = 0.3)
            doc_type = metadata.get("type", "").lower()
            if doc_type == "faq":
                authority = 1.0
            elif doc_type == "doc":
                authority = 0.9
            elif doc_type == "web":
                authority = 0.7
            elif doc_type == "chat":
                authority = 0.5
            else:
                authority = 0.7  # Default authority for unknown types

            # 3. Overlap score (weight = 0.3)
            overlap = 0.0
            if len(query_tokens) > 0:
                chunk_tokens = self.tokenize(chunk.get("text", ""))
                intersection = query_tokens.intersection(chunk_tokens)
                overlap = len(intersection) / len(query_tokens)

            # 4. Retrieval consistency score (weight = 0.2)
            # Normalize rerank_score to 0-1 across all chunks.
            # If all scores are the same or there is only one chunk, it is 1.0.
            rerank_score = chunk.get("rerank_score", 0.0)
            if score_range > 0.0:
                consistency = (rerank_score - min_s) / score_range
            else:
                consistency = 1.0

            # Compute overall confidence score
            confidence_score = (
                0.2 * freshness +
                0.3 * authority +
                0.3 * overlap +
                0.2 * consistency
            )

            # Keep all scores inside the chunk dict for observability/debugging
            chunk_copy = dict(chunk)
            chunk_copy["confidence_score"] = float(confidence_score)
            chunk_copy["confidence_subscores"] = {
                "freshness": float(freshness),
                "authority": float(authority),
                "overlap": float(overlap),
                "consistency": float(consistency),
            }
            
            # Filter: Keep only chunks with confidence_score >= 0.35
            if confidence_score >= 0.35:
                scored_chunks.append(chunk_copy)
            else:
                logger.debug(
                    "Filtering out chunk due to low confidence score %.3f: %s",
                    confidence_score, chunk.get("text", "")[:60]
                )

        # Sort the filtered list by confidence score descending
        scored_chunks.sort(key=lambda x: x["confidence_score"], reverse=True)
        logger.info(
            "Confidence scoring done. Kept %d/%d chunks.",
            len(scored_chunks), len(chunks)
        )
        return scored_chunks


# Export singleton instance
confidence_scorer = ConfidenceScorer()
