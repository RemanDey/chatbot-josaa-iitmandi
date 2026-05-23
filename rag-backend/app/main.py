"""
TASK 11 — FastAPI Entry Point (app/main.py)

Wires together the hybrid retriever, cross-encoder reranker, source confidence scorer,
LLM generator, database-backed query cache, and structured query telemetry logging.

Endpoints:
  - POST /api/chat     <- Main RAG pipeline with caching & telemetry
  - GET /health        <- Health check endpoint
  - DELETE /api/cache  <- Clears the response cache
"""

import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.retriever import retriever
from app.reranker import reranker
from app.confidence import confidence_scorer
from app.generator import generate_answer
from app.cache import cache
from app.observe import log_query_event

# ── Setup Logger ────────────────────────────────────────────────
logger = logging.getLogger("main")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Suppress noisy HuggingFace & transformers warnings/logs
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", message=".*unexpected keys.*")
warnings.filterwarnings("ignore", message=".*embeddings.position_ids.*")

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)


# ── Lifespan Context ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan events.
    Pre-loads heavy models (Embeddings and Cross-Encoder) on startup
    to prevent latency spikes on first request.
    """
    logger.info("Initializing RAG pipeline components on startup...")
    try:
        retriever.ensure_initialized()
        reranker.ensure_initialized()
        cache.ensure_initialized()
        logger.info("All pipeline components initialized successfully and ready!")
    except Exception as e:
        logger.exception("Failed to initialize RAG components during startup: %s", e)
    
    yield
    logger.info("Shutting down RAG API application.")


# ── FastAPI App Setup ───────────────────────────────────────────
app = FastAPI(
    title="IIT Mandi Chatbot RAG API",
    description="Zero-hallucination hybrid RAG pipeline for IIT Mandi student queries.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ── Pydantic Request / Response Schemas ─────────────────────────
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The query from the student.")


class SourceInfo(BaseModel):
    index: int = Field(..., description="The citation index (1-based).")
    source: str = Field(..., description="The parent source filename.")
    confidence: float = Field(..., description="The confidence score of this source chunk.")


class ChatResponse(BaseModel):
    answer: str = Field(..., description="The generated response answer string.")
    sources: List[SourceInfo] = Field(default=[], description="The inline cited sources.")
    confidence: float = Field(..., description="Overall confidence level.")
    cached: bool = Field(..., description="Whether the answer came from the cache.")


class HealthResponse(BaseModel):
    status: str = Field("ok", description="Status of the server.")


class CacheClearResponse(BaseModel):
    deleted: int = Field(..., description="Number of evicted cache entries.")


# ── API Routes ──────────────────────────────────────────────────

@app.post(
    "/api/chat",
    response_model=ChatResponse,
    summary="Ask a student support question",
    tags=["chat"]
)
async def chat(request: ChatRequest) -> Dict[str, Any]:
    """
    Process a user query through the full RAG pipeline:
    1. Cache Check (Task 9)
    2. Hybrid Retrieval (Task 2)
    3. Cross-Encoder Rerank (Task 3)
    4. Confidence Scorer (Task 4)
    5. Generation with free OpenRouter Nemotron (Task 5+6+7)
    6. Cache Storage
    7. Telemetry & Observability Logging (Task 10)
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    logger.info("Received chat query: '%s'", query[:100])
    
    start_time = time.perf_counter()

    # 1. Check cache (Task 9)
    try:
        cached_res = cache.get(query)
        if cached_res is not None:
            # Log cache hit event
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            
            # Extract scores for telemetry
            sources = cached_res.get("sources", [])
            chunk_scores = [s.get("confidence", 0.0) for s in sources]
            
            log_query_event(
                query=query,
                retrieval_count=0,
                after_confidence_filter=len(sources),
                chunk_scores=chunk_scores,
                final_confidence=cached_res["confidence"],
                response_ms=latency_ms,
                cache_hit=True,
                answer_length=len(cached_res["answer"])
            )
            return cached_res
    except Exception as e:
        logger.error("Error checking cache: %s. Continuing with normal pipeline.", e)

    # 2. Hybrid Retrieval (Task 2)
    try:
        candidates = retriever.retrieve(query, top_k=20)
    except Exception as e:
        logger.exception("Error during hybrid retrieval: %s", e)
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")

    # 3. Cross-Encoder Reranking (Task 3)
    try:
        reranked = reranker.rerank(query, candidates, top_n=5)
    except Exception as e:
        logger.exception("Error during reranking: %s", e)
        raise HTTPException(status_code=500, detail=f"Reranking failed: {e}")

    # 4. Source Confidence Scoring (Task 4)
    try:
        confident_chunks = confidence_scorer.score_chunks(query, reranked)
    except Exception as e:
        logger.exception("Error during confidence scoring: %s", e)
        raise HTTPException(status_code=500, detail=f"Confidence scoring failed: {e}")

    # 5. Constrained Generation (Task 5 + 6 + 7)
    try:
        res = generate_answer(query, confident_chunks)
    except Exception as e:
        logger.exception("Error during response generation: %s", e)
        raise HTTPException(status_code=500, detail=f"Answer generation failed: {e}")

    latency_ms = (time.perf_counter() - start_time) * 1000.0

    # 6. Store in cache (Task 9)
    try:
        cache.set(
            query=query,
            answer=res["answer"],
            sources=res["sources"],
            confidence=res["confidence"]
        )
    except Exception as e:
        logger.error("Error writing cache: %s", e)

    # 7. Telemetry & Observability logging (Task 10)
    try:
        chunk_scores = [c.get("confidence_score", 0.0) for c in confident_chunks]
        log_query_event(
            query=query,
            retrieval_count=len(candidates),
            after_confidence_filter=len(confident_chunks),
            chunk_scores=chunk_scores,
            final_confidence=res["confidence"],
            response_ms=latency_ms,
            cache_hit=False,
            answer_length=len(res["answer"])
        )
    except Exception as e:
        logger.error("Error writing observability log: %s", e)

    # Return standard response structure
    return {
        "answer": res["answer"],
        "sources": res["sources"],
        "confidence": res["confidence"],
        "cached": False
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    tags=["system"]
)
async def health() -> Dict[str, str]:
    """Returns basic service health status."""
    return {"status": "ok"}


@app.delete(
    "/api/cache",
    response_model=CacheClearResponse,
    summary="Clear the response cache database",
    tags=["system"]
)
async def clear_cache() -> Dict[str, int]:
    """Clears all stored entries in the SQLite query cache."""
    try:
        deleted_count = cache.clear()
        return {"deleted": deleted_count}
    except Exception as e:
        logger.error("Failed to clear cache: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {e}")
