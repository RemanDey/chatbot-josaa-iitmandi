"""
TASK 10 — Observability (app/observe.py)

Logs structured JSON metrics for every RAG query event to logs/rag.log.
Uses rotating file handler (max 5MB, 3 backups).

Exports:
  - `log_query_event(query, retrieval_count, after_confidence_filter, chunk_scores, final_confidence, response_ms, cache_hit, answer_length)`
  - `RAGObserver` class
  - `observer` (singleton instance of RAGObserver)
"""

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import List, Dict, Any

# ── Logger Setup ────────────────────────────────────────────────
LOG_DIR = "logs"
LOG_FILE_PATH = os.path.join(LOG_DIR, "rag.log")
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

os.makedirs(LOG_DIR, exist_ok=True)

# Define a private logger to prevent collision with other handlers
_logger = logging.getLogger("rag_observer")
_logger.setLevel(logging.INFO)
_logger.propagate = False  # Avoid duplicates in standard output streams

# Ensure only one handler is configured
if not _logger.handlers:
    _handler = RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8"
    )
    # Simple formatter that just outputs the logged text message
    _formatter = logging.Formatter("%(message)s")
    _handler.setFormatter(_formatter)
    _logger.addHandler(_handler)


class RAGObserver:
    """
    RAG Pipeline observer for tracking telemetry, query details, latencies, and cache statistics.
    """

    def log_event(
        self,
        query: str,
        retrieval_count: int,
        after_confidence_filter: int,
        chunk_scores: List[float],
        final_confidence: float,
        response_ms: float,
        cache_hit: bool,
        answer_length: int
    ) -> None:
        """
        Record a single query event to the RAG log file as a flat JSON string.
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query.strip(),
            "retrieval_count": int(retrieval_count),
            "after_confidence_filter": int(after_confidence_filter),
            "chunk_scores": [float(s) for s in chunk_scores],
            "final_confidence": float(final_confidence),
            "response_ms": float(response_ms),
            "cache_hit": bool(cache_hit),
            "answer_length": int(answer_length)
        }
        
        try:
            # Serialize the dictionary to a single compact line
            log_line = json.dumps(event, ensure_ascii=False)
            _logger.info(log_line)
        except Exception as e:
            # Fallback print/log in case serialization fails
            sys_logger = logging.getLogger("observe")
            sys_logger.error("Failed to log RAG query event: %s", e)


# Export singleton observer instance
observer = RAGObserver()


# Export helper function for convenience
def log_query_event(
    query: str,
    retrieval_count: int,
    after_confidence_filter: int,
    chunk_scores: List[float],
    final_confidence: float,
    response_ms: float,
    cache_hit: bool,
    answer_length: int
) -> None:
    """Log structured query metrics using the singleton observer."""
    observer.log_event(
        query=query,
        retrieval_count=retrieval_count,
        after_confidence_filter=after_confidence_filter,
        chunk_scores=chunk_scores,
        final_confidence=final_confidence,
        response_ms=response_ms,
        cache_hit=cache_hit,
        answer_length=answer_length
    )
