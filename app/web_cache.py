import hashlib
import json
import sqlite3
import os
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("web_cache")

class WebCache:
    def __init__(self, db_path: str = "data/web_cache.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gemini_web_cache (
                    query_hash TEXT PRIMARY KEY,
                    normalized_query TEXT NOT NULL,
                    original_query TEXT NOT NULL,
                    response_text TEXT,
                    extracted_claims TEXT,  -- JSON string of list of claims
                    entity TEXT,
                    categories TEXT,        -- JSON string of list of categories
                    query_type TEXT,
                    timestamp TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def _normalize(self, query: str) -> str:
        """Normalize query to ensure consistent cache keys."""
        q = query.lower().strip()
        # Remove common punctuation
        import re
        q = re.sub(r'[^\w\s]', '', q)
        # Collapse multiple spaces into one
        q = re.sub(r'\s+', ' ', q)
        return q.strip()

    def _get_hash(self, query: str) -> str:
        normalized = self._normalize(query)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get_ttl_duration(self, query_type: str) -> timedelta:
        """Get the TTL duration for a given query type."""
        qt = query_type.lower()
        if qt == "placement_query":
            return timedelta(hours=24)
        elif qt == "cutoff_query":
            return timedelta(hours=12)
        elif qt == "latest_updates":
            return timedelta(hours=6)
        else:
            return timedelta(days=7)

    def get(self, query: str) -> dict:
        """
        Look up a query in the cache. 
        Returns the row as a dict if found and not expired, otherwise None.
        """
        query_hash = self._get_hash(query)
        now_str = datetime.now(timezone.utc).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM gemini_web_cache WHERE query_hash = ?", 
                (query_hash,)
            )
            row = cursor.fetchone()
            
            if row is None:
                return None
                
            expires_at = datetime.fromisoformat(row["expires_at"])
            now = datetime.now(timezone.utc)
            
            if now > expires_at:
                logger.info("Cache entry expired for: %s (expired at %s)", query, row["expires_at"])
                # We can optionally delete expired entries here
                cursor.execute(
                    "DELETE FROM gemini_web_cache WHERE query_hash = ?", 
                    (query_hash,)
                )
                conn.commit()
                return None
                
            # Increment hit count
            cursor.execute(
                "UPDATE gemini_web_cache SET hit_count = hit_count + 1 WHERE query_hash = ?",
                (query_hash,)
            )
            conn.commit()
            
            # Convert row to dict and parse JSON fields
            result = dict(row)
            try:
                result["extracted_claims"] = json.loads(row["extracted_claims"]) if row["extracted_claims"] else []
            except Exception as e:
                logger.warning("Failed to parse extracted_claims from cache: %s", e)
                result["extracted_claims"] = []
                
            try:
                result["categories"] = json.loads(row["categories"]) if row["categories"] else []
            except Exception as e:
                logger.warning("Failed to parse categories from cache: %s", e)
                result["categories"] = []
                
            return result

    def set(self, query: str, response_text: str, extracted_claims: list = None, 
            entity: str = None, categories: list = None, query_type: str = "general"):
        """Save an entry into the cache with calculated expires_at."""
        query_hash = self._get_hash(query)
        normalized = self._normalize(query)
        
        now = datetime.now(timezone.utc)
        ttl = self.get_ttl_duration(query_type)
        expires_at = now + ttl
        
        now_str = now.isoformat()
        expires_at_str = expires_at.isoformat()
        
        claims_json = json.dumps(extracted_claims or [])
        categories_json = json.dumps(categories or [])
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO gemini_web_cache (
                    query_hash, normalized_query, original_query, response_text, 
                    extracted_claims, entity, categories, query_type, timestamp, expires_at, hit_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT hit_count FROM gemini_web_cache WHERE query_hash = ?), 0))
            """, (
                query_hash, normalized, query, response_text, 
                claims_json, entity, categories_json, query_type, now_str, expires_at_str, query_hash
            ))
            conn.commit()
            logger.info("Cached query '%s' of type '%s' (expires in %s)", query, query_type, ttl)
