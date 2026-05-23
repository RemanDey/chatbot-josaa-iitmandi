"""
TASK 9 — Caching + Memory Layer (app/cache.py)

Uses a local SQLite database (data/cache.db) to cache RAG query responses.
Caches expire after 24 hours. Exposes query hash lookup, cache storage,
and cache clear operations.

Exports:
  - `ResponseCache` class
  - `cache` (singleton instance of ResponseCache)
"""

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger("cache")

# ── Constants ───────────────────────────────────────────────────
CACHE_DB_PATH = "data/cache.db"
CACHE_TABLE_NAME = "query_cache"
CACHE_EXPIRATION_SECONDS = 24 * 3600  # 24 hours


class ResponseCache:
    """
    SQLite-backed response cache for the RAG pipeline.
    """

    def __init__(self, db_path: str = CACHE_DB_PATH):
        self.db_path = db_path
        self._initialized = False

    def ensure_initialized(self) -> None:
        """Create the cache directory and table if they don't exist."""
        if self._initialized:
            return

        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {CACHE_TABLE_NAME} (
                        query_hash TEXT PRIMARY KEY,
                        query TEXT,
                        answer TEXT,
                        sources TEXT,       -- JSON string
                        confidence REAL,
                        created_at TEXT
                    )
                """)
                conn.commit()
            self._initialized = True
            logger.info("SQLite cache initialized successfully at %s", self.db_path)
        except Exception as e:
            logger.error("Failed to initialize SQLite cache at %s: %s", self.db_path, e)
            raise

    def _get_hash(self, query: str) -> str:
        """Compute sha256 hash of the normalized query."""
        return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve response from the cache if it exists and has not expired.

        Args:
            query: The user query string.

        Returns:
            Dict response with 'answer', 'sources', 'confidence', and 'cached' = True if found,
            else None.
        """
        self.ensure_initialized()
        query_hash = self._get_hash(query)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT answer, sources, confidence, created_at FROM {CACHE_TABLE_NAME} WHERE query_hash = ?",
                    (query_hash,)
                )
                row = cursor.fetchone()

                if row is None:
                    return None

                created_at_str = row["created_at"]
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    now = datetime.now(timezone.utc)
                    age_seconds = (now - created_at).total_seconds()
                    
                    if age_seconds >= CACHE_EXPIRATION_SECONDS:
                        logger.info("Cache hit but expired (age: %.1f hours). Evicting.", age_seconds / 3600.0)
                        self.evict(query_hash)
                        return None
                except Exception as ex:
                    logger.warning("Error parsing cache timestamp '%s': %s. Evicting.", created_at_str, ex)
                    self.evict(query_hash)
                    return None

                sources_list = []
                if row["sources"]:
                    try:
                        sources_list = json.loads(row["sources"])
                    except Exception as json_err:
                        logger.error("Error parsing cached sources JSON: %s", json_err)

                logger.info("Cache HIT for query: '%s'", query[:50])
                return {
                    "answer": row["answer"],
                    "sources": sources_list,
                    "confidence": float(row["confidence"]),
                    "cached": True
                }

        except Exception as e:
            logger.error("Error reading cache for query '%s': %s", query[:50], e)
            return None

    def set(self, query: str, answer: str, sources: List[Dict[str, Any]], confidence: float) -> None:
        """
        Store a new query response in the cache.

        Args:
            query: The user query.
            answer: The generated text answer.
            sources: List of source dictionaries.
            confidence: The confidence float score.
        """
        self.ensure_initialized()
        query_hash = self._get_hash(query)
        sources_json = json.dumps(sources)
        created_at_str = datetime.now(timezone.utc).isoformat()

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {CACHE_TABLE_NAME} (query_hash, query, answer, sources, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (query_hash, query.strip(), answer, sources_json, float(confidence), created_at_str)
                )
                conn.commit()
            logger.info("Cache entry stored for query: '%s'", query[:50])
        except Exception as e:
            logger.error("Error storing cache entry for query '%s': %s", query[:50], e)

    def evict(self, query_hash: str) -> None:
        """Delete an expired/corrupt cache entry by query_hash."""
        self.ensure_initialized()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM {CACHE_TABLE_NAME} WHERE query_hash = ?", (query_hash,))
                conn.commit()
            logger.debug("Evicted query hash %s from cache", query_hash)
        except Exception as e:
            logger.error("Error evicting query hash %s from cache: %s", query_hash, e)

    def clear(self) -> int:
        """
        Clear all cached queries.

        Returns:
            Number of deleted cache rows.
        """
        self.ensure_initialized()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM {CACHE_TABLE_NAME}")
                deleted_rows = cursor.rowcount
                conn.commit()
            logger.info("Cleared response cache. Deleted %d entries.", deleted_rows)
            return deleted_rows
        except Exception as e:
            logger.error("Error clearing response cache: %s", e)
            return 0


# Export singleton instance
cache = ResponseCache()
