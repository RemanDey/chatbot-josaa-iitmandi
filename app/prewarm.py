#!/usr/bin/env python3
"""
TASK 9 — Prewarm Web Claims Cache (app/prewarm.py)

Precomputes and caches structured web claims for all key entities, branches, and categories:
- IIT Mandi EE
- IIT Mandi CSE
- IIT Mandi Mechanical
- IIT Mandi GE
- IIT Mandi placements
- IIT Mandi cutoff
- IIT Mandi vs all iits

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

from app.cache import cache
from app.generator import generator, normalize_entity_category, verify_claim

logger = logging.getLogger("prewarm")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


PREWARM_TOPICS = [
    # ── IIT Mandi EE ──
    {"entity": "IIT Mandi EE", "aspect": "placements", "query": "IIT Mandi EE placements packages average"},
    {"entity": "IIT Mandi EE", "aspect": "curriculum", "query": "IIT Mandi EE B.Tech curriculum course credits"},
    {"entity": "IIT Mandi EE", "aspect": "research", "query": "IIT Mandi EE faculty research labs"},
    {"entity": "IIT Mandi EE", "aspect": "software_transition", "query": "IIT Mandi EE software industry jobs transition"},
    
    # ── IIT Mandi CSE ──
    {"entity": "IIT Mandi CSE", "aspect": "placements", "query": "IIT Mandi CSE placements package stats"},
    {"entity": "IIT Mandi CSE", "aspect": "curriculum", "query": "IIT Mandi CSE B.Tech course syllabus rigor"},
    {"entity": "IIT Mandi CSE", "aspect": "research", "query": "IIT Mandi CSE faculty research areas"},
    {"entity": "IIT Mandi CSE", "aspect": "software_transition", "query": "IIT Mandi CSE coding culture careers"},

    # ── IIT Mandi ME ──
    {"entity": "IIT Mandi Mechanical", "aspect": "placements", "query": "IIT Mandi Mechanical engineering placements"},
    {"entity": "IIT Mandi Mechanical", "aspect": "curriculum", "query": "IIT Mandi Mechanical curriculum course syllabus"},
    {"entity": "IIT Mandi Mechanical", "aspect": "research", "query": "IIT Mandi Mechanical engineering labs research"},
    {"entity": "IIT Mandi Mechanical", "aspect": "software_transition", "query": "IIT Mandi Mechanical B.Tech IT sector software transition"},

    # ── IIT Mandi GE (General Engineering / General Studies / Cutoffs) ──
    {"entity": "IIT Mandi GE", "aspect": "cutoffs", "query": "IIT Mandi opening and closing ranks JoSAA"},
    {"entity": "IIT Mandi GE", "aspect": "campus_life", "query": "IIT Mandi campus facilities hostels life"},

    # ── General Placements & Cutoffs ──
    {"entity": "IIT Mandi", "aspect": "placements", "query": "IIT Mandi overall placements statistics average highest packages"},
    {"entity": "IIT Mandi", "aspect": "cutoffs", "query": "IIT Mandi JoSAA cutoff ranks for all branches"},
    {"entity": "IIT Mandi", "aspect": "general", "query": "IIT Mandi vs all other newer IITs comparison"}
]


async def prewarm_cache():
    """Run structured web claim prewarming."""
    logger.info("Initializing prewarm process for %d key topics...", len(PREWARM_TOPICS))
    cache.ensure_initialized()
    
    success_count = 0
    fail_count = 0
    
    for idx, topic in enumerate(PREWARM_TOPICS, 1):
        ent = topic["entity"]
        aspect = topic["aspect"]
        query = topic["query"]
        
        norm_entity, norm_category = normalize_entity_category(ent, aspect)
        logger.info("[%d/%d] Prewarming Cache Namespace: (%s, %s) with query: '%s'", 
                    idx, len(PREWARM_TOPICS), norm_entity, norm_category, query)
        
        try:
            # Check if cache already has valid claims to avoid redundant Gemini calls
            existing = cache.get_cached_web_claims(norm_entity, norm_category)
            if existing is not None and len(existing) > 0:
                logger.info("-> Cache hit and fresh for (%s, %s). Skipping query.", norm_entity, norm_category)
                success_count += 1
                continue
                
            # Fetch fresh web claims from Gemini
            fresh_claims = await generator.extract_web_claims(query)
            if not fresh_claims:
                logger.warning("-> No claims returned for: '%s'", query)
                fail_count += 1
                await asyncio.sleep(4)
                continue
                
            # Verify and store claims
            verified_claims = []
            for c in fresh_claims:
                c["origin"] = "web"
                c["entity"] = norm_entity
                c["category"] = norm_category
                verify_claim(c)
                if not c.get("rejected", False):
                    verified_fresh = {
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
                cache.set_cached_web_claims(norm_entity, norm_category, verified_claims)
                logger.info("-> Successfully cached %d verified claims for (%s, %s)", 
                            len(verified_claims), norm_entity, norm_category)
                success_count += 1
            else:
                logger.warning("-> All extracted claims were filtered out for: '%s'", query)
                fail_count += 1
                
        except Exception as e:
            logger.error("-> Failed to prewarm (%s, %s): %s", norm_entity, norm_category, e)
            fail_count += 1
            
        # Add rate limit delay
        await asyncio.sleep(4)
            
    logger.info("Cache prewarming complete. Success: %d, Failed: %d", success_count, fail_count)


if __name__ == "__main__":
    asyncio.run(prewarm_cache())

