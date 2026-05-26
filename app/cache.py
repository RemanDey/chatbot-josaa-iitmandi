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
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger("cache")

# ── Constants ───────────────────────────────────────────────────
CACHE_DB_PATH = "data/cache.db"
CACHE_TABLE_NAME = "query_cache"
CACHE_EXPIRATION_SECONDS = 24 * 3600  # 24 hours


def get_normalized_query(query: str) -> str:
    """
    Normalizes the query string to map variations to the same semantic representation.
    """
    q = query.lower().strip()
    q = re.sub(r"[^\w\s]", " ", q)  # remove punctuation
    q = " ".join(q.split())          # normalize whitespace
    
    # Standard replacement mappings
    replacements = {
        "electrical engineering": "ee",
        "electrical": "ee",
        "computer science and engineering": "cse",
        "computer science": "cse",
        "mechanical engineering": "me",
        "mechanical": "me",
        "civil engineering": "ce",
        "civil": "ce",
        "data science": "ds",
        "data science and engineering": "ds",
        "overall placements": "placements",
        "placement statistics": "placements",
        "placement stats": "placements",
        "average package": "placements",
        "cutoff ranks": "cutoffs",
        "opening and closing ranks": "cutoffs",
        "josaa cutoff": "cutoffs"
    }
    
    # Apply replacement mappings
    for word, rep in replacements.items():
        q = re.sub(rf"\b{word}\b", rep, q)
        
    # Differentiate comparison intent vs single branch info
    is_comparison = any(w in q for w in ["vs", "compare", "comparison", "better", "difference"])
    
    # Extract entities/branches present
    branches = []
    if "ee" in q: branches.append("ee")
    if "cse" in q: branches.append("cse")
    if "me" in q: branches.append("me")
    if "ce" in q: branches.append("ce")
    if "ds" in q: branches.append("ds")
    
    # Sort branches to make comparison order-independent
    branches.sort()
    
    # Reconstruct a highly normalized semantic representation
    if branches:
        if is_comparison:
            return f"comparison:{':'.join(branches)}"
        else:
            # Check if specific aspects are requested
            aspects = []
            if "placement" in q or "salary" in q or "jobs" in q or "package" in q:
                aspects.append("placements")
            if "cutoff" in q or "rank" in q or "josaa" in q:
                aspects.append("cutoffs")
            if "curriculum" in q or "syllabus" in q or "rigor" in q or "course" in q:
                aspects.append("curriculum")
            if "research" in q or "faculty" in q or "projects" in q:
                aspects.append("research")
                
            aspects.sort()
            aspect_str = f":{':'.join(aspects)}" if aspects else ""
            return f"branch:{branches[0]}{aspect_str}"
    
    return q


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
                        created_at TEXT,
                        expires_at TEXT
                    )
                """)
                # Run migrations to ensure expires_at is present
                cursor.execute(f"PRAGMA table_info({CACHE_TABLE_NAME})")
                columns = [col[1] for col in cursor.fetchall()]
                if "expires_at" not in columns:
                    cursor.execute(f"ALTER TABLE {CACHE_TABLE_NAME} ADD COLUMN expires_at TEXT")
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS claims_cache (
                        key TEXT PRIMARY KEY,
                        claims_json TEXT,
                        created_at TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS web_claims (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        entity TEXT NOT NULL,
                        category TEXT NOT NULL,
                        claim TEXT NOT NULL,
                        source_url TEXT,
                        source_name TEXT,
                        source_type TEXT,
                        source_year INTEGER,
                        confidence REAL,
                        retrieved_at TIMESTAMP,
                        expires_at TIMESTAMP,
                        query_hash TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS entity_summary_cache (
                        entity TEXT PRIMARY KEY,
                        claims_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        reason TEXT,
                        retrieved_at TIMESTAMP NOT NULL,
                        expires_at TIMESTAMP NOT NULL
                    )
                """)
                conn.commit()
            self._initialized = True
            logger.info("SQLite cache initialized successfully at %s", self.db_path)
        except Exception as e:
            logger.error("Failed to initialize SQLite cache at %s: %s", self.db_path, e)
            raise

    def _get_ttl_for_type(self, query_type: str) -> timedelta:
        """Get the TTL duration for a given query type."""
        qt = query_type.lower()
        if qt == "placement_query":
            return timedelta(hours=24)
        elif qt == "cutoff_query":
            return timedelta(hours=12)
        elif qt == "latest_updates":
            return timedelta(hours=6)
        elif qt in ["campus_life", "fee_query"]:
            return timedelta(days=7)
        else:
            return timedelta(hours=24)

    def _get_hash(self, query: str) -> str:
        """Compute sha256 hash of the normalized query."""
        normalized = get_normalized_query(query)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
                    f"SELECT answer, sources, confidence, created_at, expires_at FROM {CACHE_TABLE_NAME} WHERE query_hash = ?",
                    (query_hash,)
                )
                row = cursor.fetchone()

                if row is None:
                    return None

                created_at_str = row["created_at"]
                expires_at_str = row["expires_at"] if "expires_at" in row.keys() else None
                
                try:
                    now = datetime.now(timezone.utc)
                    if expires_at_str:
                        expires_at = datetime.fromisoformat(expires_at_str)
                        if now > expires_at:
                            logger.info("Cache hit but expired (expired at %s). Evicting.", expires_at_str)
                            self.evict(query_hash)
                            return None
                    else:
                        created_at = datetime.fromisoformat(created_at_str)
                        age_seconds = (now - created_at).total_seconds()
                        if age_seconds >= CACHE_EXPIRATION_SECONDS:
                            logger.info("Cache hit but expired (age: %.1f hours). Evicting.", age_seconds / 3600.0)
                            self.evict(query_hash)
                            return None
                except Exception as ex:
                    logger.warning("Error parsing cache timestamp: %s. Evicting.", ex)
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

    def set(self, query: str, answer: str, sources: List[Dict[str, Any]], confidence: float, query_type: str = "general") -> None:
        """
        Store a new query response in the cache with query-type-specific TTL.
        """
        self.ensure_initialized()
        query_hash = self._get_hash(query)
        sources_json = json.dumps(sources)
        now = datetime.now(timezone.utc)
        created_at_str = now.isoformat()
        
        ttl = self._get_ttl_for_type(query_type)
        expires_at_str = (now + ttl).isoformat()

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {CACHE_TABLE_NAME} (query_hash, query, answer, sources, confidence, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (query_hash, query.strip(), answer, sources_json, float(confidence), created_at_str, expires_at_str)
                )
                conn.commit()
            logger.info("Cache entry stored for query: '%s' of type '%s' (expires in %s)", query[:50], query_type, ttl)
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

    def get_cached_claims(self, entity: str, category: str, year: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        """Retrieve structured claims list for a given entity, category, and year if not expired."""
        self.ensure_initialized()
        cache_key = f"{entity}:{category}:{year}"
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT claims_json, created_at FROM claims_cache WHERE key = ?",
                    (cache_key,)
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
                        logger.info("Claims cache hit but expired for key: %s. Evicting.", cache_key)
                        cursor.execute("DELETE FROM claims_cache WHERE key = ?", (cache_key,))
                        conn.commit()
                        return None
                except Exception:
                    cursor.execute("DELETE FROM claims_cache WHERE key = ?", (cache_key,))
                    conn.commit()
                    return None

                logger.info("Claims cache HIT for key: %s", cache_key)
                return json.loads(row["claims_json"])
        except Exception as e:
            logger.error("Error reading claims cache for %s: %s", cache_key, e)
            return None

    def set_cached_claims(self, entity: str, category: str, year: Optional[int], claims: List[Dict[str, Any]]) -> None:
        """Cache a list of structured claims."""
        self.ensure_initialized()
        cache_key = f"{entity}:{category}:{year}"
        claims_json = json.dumps(claims)
        created_at_str = datetime.now(timezone.utc).isoformat()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO claims_cache (key, claims_json, created_at) VALUES (?, ?, ?)",
                    (cache_key, claims_json, created_at_str)
                )
                conn.commit()
            logger.info("Stored structured claims in cache for key: %s", cache_key)
        except Exception as e:
            logger.error("Error storing claims cache for %s: %s", cache_key, e)

    def clear(self) -> int:
        """
        Clear all cached queries and claims.

        Returns:
            Number of deleted cache rows across all tables.
        """
        self.ensure_initialized()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM {CACHE_TABLE_NAME}")
                deleted_rows = cursor.rowcount
                cursor.execute("DELETE FROM claims_cache")
                deleted_rows += cursor.rowcount
                cursor.execute("DELETE FROM web_claims")
                deleted_rows += cursor.rowcount
                conn.commit()
            logger.info("Cleared response, claims, and web_claims cache. Deleted %d entries total.", deleted_rows)
            return deleted_rows
        except Exception as e:
            logger.error("Error clearing response/claims cache: %s", e)
            return 0

    def get_cached_web_claims(self, entity: str, category: str) -> Optional[List[Dict[str, Any]]]:
        """
        Lookup cached structured web claims in SQLite 'web_claims' table by normalized entity and category.
        If cache hit and not expired, return list of claims, else None.
        """
        self.ensure_initialized()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT entity, category, claim, source_url, source_name, source_type, source_year, confidence 
                    FROM web_claims 
                    WHERE entity = ? AND category = ? AND expires_at > ?
                    """,
                    (entity, category, now_str)
                )
                rows = cursor.fetchall()
                if not rows:
                    return None
                
                claims = []
                for row in rows:
                    claims.append({
                        "entity": row["entity"],
                        "category": row["category"],
                        "claim": row["claim"],
                        "source_url": row["source_url"],
                        "source_name": row["source_name"],
                        "source_type": row["source_type"],
                        "source_year": row["source_year"],
                        "confidence": row["confidence"],
                        "origin": "web"
                    })
                logger.info("Web claims cache HIT for entity: '%s', category: '%s' (%d claims)", entity, category, len(claims))
                return claims
        except Exception as e:
            logger.error("Error reading web claims cache for %s:%s: %s", entity, category, e)
            return None

    def set_cached_web_claims(self, entity: str, category: str, claims: List[Dict[str, Any]], query_hash: Optional[str] = None) -> None:
        """
        Cache a list of structured web claims into SQLite 'web_claims' table.
        Each claim is saved as a separate row. Origin is always "web".
        """
        self.ensure_initialized()
        retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # First delete any existing cache entries for this entity and category to avoid duplicates
                cursor.execute("DELETE FROM web_claims WHERE entity = ? AND category = ?", (entity, category))
                
                for c in claims:
                    # RAG claims must NEVER be saved to the web cache!
                    if c.get("origin") == "rag":
                        continue
                    
                    cursor.execute(
                        """
                        INSERT INTO web_claims (entity, category, claim, source_url, source_name, source_type, source_year, confidence, retrieved_at, expires_at, query_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entity,
                            category,
                            c.get("claim", c.get("text", "")),
                            c.get("source_url"),
                            c.get("source_name", "Gemini Web Search"),
                            c.get("source_type", "Web Search"),
                            c.get("source_year"),
                            float(c.get("confidence", 0.5)),
                            retrieved_at,
                            expires_at,
                            query_hash
                        )
                    )
                conn.commit()
            logger.info("Stored %d web claims in cache for %s:%s", len(claims), entity, category)
        except Exception as e:
            logger.error("Error storing web claims in cache for %s:%s: %s", entity, category, e)

    def cleanup_expired_web_claims(self) -> int:
        """
        Delete expired web claims from SQLite cache.
        """
        self.ensure_initialized()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM web_claims WHERE expires_at < ?", (now_str,))
                deleted = cursor.rowcount
                conn.commit()
            logger.info("Daily cleanup of web claims complete. Deleted %d expired claims.", deleted)
            return deleted
        except Exception as e:
            logger.error("Failed to clean up expired web claims: %s", e)
            return 0

    def get_cached_entity_summary(self, entity: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached claims summary for an entity.
        Returns a dict containing 'claims', 'status', and 'reason', or None if expired/not found.
        """
        self.ensure_initialized()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT claims_json, status, reason, expires_at 
                    FROM entity_summary_cache 
                    WHERE entity = ? AND expires_at > ?
                    """,
                    (entity.upper().strip(), now_str)
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                
                logger.info("Entity summary cache HIT for entity: '%s' (status: %s)", entity, row["status"])
                return {
                    "claims": json.loads(row["claims_json"]),
                    "status": row["status"],
                    "reason": row["reason"]
                }
        except Exception as e:
            logger.error("Error reading entity summary cache for %s: %s", entity, e)
            return None

    def set_cached_entity_summary(self, entity: str, claims: List[Dict[str, Any]], status: str = "success", reason: Optional[str] = None) -> None:
        """
        Caches the entire structured web claims for an entity with expiration and status.
        """
        self.ensure_initialized()
        retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        claims_json = json.dumps(claims)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO entity_summary_cache (entity, claims_json, status, reason, retrieved_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (entity.upper().strip(), claims_json, status, reason, retrieved_at, expires_at)
                )
                conn.commit()
            logger.info("Stored entity summary cache for %s (claims: %d, status: %s)", entity, len(claims), status)
        except Exception as e:
            logger.error("Error storing entity summary cache for %s: %s", entity, e)


# Export singleton instance
cache = ResponseCache()

