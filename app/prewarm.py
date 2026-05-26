#!/usr/bin/env python3
"""
TASK 9 — Prewarm Web Claims Cache (app/prewarm.py)

Precomputes and caches structured web claims for all key entities, branches, and categories:
- IIT Mandi EE
- IIT Mandi CSE
- IIT Mandi ME
- IIT Mandi CE
- IIT Mandi DS
- IIT Mandi GE
- IIT Mandi

This minimizes real-time Gemini API calls and search grounding latency during counseling traffic spikes.
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone

# Ensure project root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.web_cache import WebCache
from app.generator import generator, normalize_entity_category, verify_claim

logger = logging.getLogger("prewarm")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

PREWARM_ENTITIES = [
    "IIT Mandi EE",
    "IIT Mandi CSE",
    "IIT Mandi ME",
    "IIT Mandi CE",
    "IIT Mandi DS",
    "IIT Mandi GE",
    "IIT Mandi"
]

async def prewarm_cache():
    """Run structured web claim prewarming."""
    logger.info("Initializing prewarm process for %d key entities...", len(PREWARM_ENTITIES))
    cache = WebCache()
    cache.ensure_initialized()
    
    success_count = 0
    fail_count = 0
    
    for idx, ent in enumerate(PREWARM_ENTITIES, 1):
        # Normalize the entity to be 100% sure we use the correct unified key
        norm_entity, _ = normalize_entity_category(ent, "general")
        logger.info("[%d/%d] Prewarming Cache for Entity: '%s' (normalized: '%s')", 
                    idx, len(PREWARM_ENTITIES), ent, norm_entity)
        
        try:
            # Check if cache already has valid claims to avoid redundant Gemini calls
            existing = cache.get(norm_entity)
            if existing is not None and existing.get("extracted_claims"):
                logger.info("-> Cache hit and fresh for '%s'. Skipping query.", norm_entity)
                success_count += 1
                continue
                
            # Fetch fresh web claims from Gemini via unified entity retrieval
            fresh_claims = await generator.extract_web_claims_for_entity(norm_entity)
            if not fresh_claims:
                logger.warning("-> No claims returned for entity: '%s'", norm_entity)
                fail_count += 1
                await asyncio.sleep(4)
                continue
                
            # Verify and store claims
            verified_claims = []
            for c in fresh_claims:
                c["origin"] = "web"
                # Normalize sub-claim entity & category
                norm_ent, norm_cat = normalize_entity_category(norm_entity, c.get("category", "general"))
                c["entity"] = norm_ent
                c["category"] = norm_cat
                verify_claim(c)
                if not c.get("rejected", False):
                    verified_fresh = {
                        "entity": c["entity"],
                        "category": c["category"],
                        "claim": c.get("text", c.get("claim", "")),
                        "source_url": c.get("source_url"),
                        "source_name": c.get("source_name", "Gemini Web Search"),
                        "source_type": c.get("source_type", "Web Search"),
                        "source_year": c.get("source_year"),
                        "confidence": float(c.get("confidence", 0.5)),
                        "origin": "web"
                    }
                    verified_claims.append(verified_fresh)
            
            if verified_claims:
                cache.set(norm_entity, "", extracted_claims=verified_claims, entity=norm_entity, query_type="general")
                logger.info("-> Successfully cached %d verified claims for '%s'", 
                            len(verified_claims), norm_entity)
                success_count += 1
            else:
                logger.warning("-> All extracted claims were filtered out for entity: '%s'", norm_entity)
                # Still cache an empty list to avoid repeatedly calling the API
                cache.set(norm_entity, "", extracted_claims=[], entity=norm_entity, query_type="general")
                fail_count += 1
                
        except Exception as e:
            logger.error("-> Failed to prewarm entity '%s': %s", norm_entity, e)
            fail_count += 1
            
        # Add rate limit delay to avoid hitting 429
        await asyncio.sleep(4)
            
    logger.info("Cache prewarming complete. Success: %d, Failed: %d", success_count, fail_count)

if __name__ == "__main__":
    asyncio.run(prewarm_cache())
