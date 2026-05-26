"""
TASK 11 — FastAPI Entry Point (app/main.py)

Wires together the hybrid retriever, cross-encoder reranker, source confidence scorer,
LLM generator, database-backed query cache, and structured query telemetry logging.

Endpoints:
  - POST /api/chat     <- Main RAG pipeline with caching & telemetry
  - GET /health        <- Health check endpoint
  - DELETE /api/cache  <- Clears the response cache
"""

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Any


from fastapi import FastAPI, HTTPException, Query, Request, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.retriever import retriever
from app.reranker import reranker
from app.confidence import confidence_scorer
from app.generator import generate_answer, decompose_query, generator, classify_query_rich
from app.web_cache import WebCache
cache = WebCache()
from app.observe import log_query_event, log_telemetry
from app.config import settings

# ── Setup Logger ────────────────────────────────────────────────
logger = logging.getLogger("main")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# ── Greetings Set ───────────────────────────────────────────────
GREETINGS = {
    "hi", "hello", "hey", "hii", "helo", "sup", "yo", "thanks",
    "thank you", "ok", "okay", "bye", "good morning", "good evening", "namaste"
}

# Initialize Limiter
limiter = Limiter(key_func=get_remote_address)

# Suppress noisy HuggingFace & transformers warnings/logs
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", message=".*unexpected keys.*")
warnings.filterwarnings("ignore", message=".*embeddings.position_ids.*")

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)



# ── Lifespan Context ────────────────────────────────────────────
def initialize_pipeline() -> Dict[str, str]:
    """Initialize the expensive RAG components and return their status."""
    retriever.ensure_initialized()
    reranker.ensure_initialized()
    cache.ensure_initialized()
    return {
        "retriever": "ready",
        "reranker": "ready",
        "cache": "ready",
    }


def readiness_checks() -> Dict[str, bool]:
    """Check required local deployment files without loading transformer models."""
    return {
        "chroma_db_path": Path(settings.chroma_db_path).exists(),
        "bm25_pickle_file": Path(settings.bm25_pickle_file).exists(),
        "cache_initialized": cache._initialized,
    }


security = HTTPBearer(auto_error=False)


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> None:
    """Validate Bearer API token if settings.api_key is configured."""
    expected_key = settings.api_key.strip()
    if not expected_key:
        return
    if not credentials or credentials.credentials != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def verify_warmup_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> None:
    """Validate Bearer warmup/admin token if settings.warmup_token is configured."""
    expected_token = settings.warmup_token.strip()
    if not expected_token:
        return
    if not credentials or credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid or missing warmup token.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan events.
    Pre-loads heavy models (Embeddings and Cross-Encoder) on startup
    to prevent latency spikes on first request.
    """
    logger.info("Starting RAG API application in %s mode.", settings.app_env)
    try:
        if settings.eager_load_models:
            logger.info("EAGER_LOAD_MODELS is enabled. Initializing RAG components on startup...")
            initialize_pipeline()
            logger.info("All pipeline components initialized successfully and ready!")
        else:
            logger.info("EAGER_LOAD_MODELS is disabled. Initializing lightweight cache only.")
            cache.ensure_initialized()
            logger.info("Cache initialized. Retrieval models will load on first warmup or chat request.")
    except Exception as e:
        logger.exception("Failed to initialize RAG components during startup: %s", e)
        if settings.eager_load_models:
            raise
    
    yield
    logger.info("Shutting down RAG API application.")


# ── FastAPI App Setup ───────────────────────────────────────────
app = FastAPI(
    title="IIT Mandi Chatbot RAG API",
    description="Zero-hallucination hybrid RAG pipeline for IIT Mandi student queries.",
    version="1.0.0",
    lifespan=lifespan
)

# SlowAPI setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Global 500 exception handler to sanitize error logs and prevent private token leaks
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception occurred: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )

# Enable CORS for frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ── Pydantic Request / Response Schemas ─────────────────────────
class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message sender (user or assistant).")
    content: str = Field(..., description="Content of the message.")

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="The query from the student.")
    history: List[ChatMessage] = Field(default=[], description="Previous conversation context.")


class SourceInfo(BaseModel):
    index: int = Field(..., description="The citation index (1-based).")
    source: str = Field(..., description="The parent source filename.")


class ChatResponse(BaseModel):
    answer: str = Field(..., description="The generated response answer string.")
    sources: List[SourceInfo] = Field(default=[], description="The inline cited sources.")
    cached: bool = Field(..., description="Whether the answer came from the cache.")


class HealthResponse(BaseModel):
    status: str = Field("ok", description="Status of the server.")


class ReadinessResponse(BaseModel):
    status: str = Field(..., description="Readiness status.")
    checks: Dict[str, bool] = Field(..., description="Readiness checks.")


class WarmupResponse(BaseModel):
    status: str = Field(..., description="Warmup status.")
    components: Dict[str, str] = Field(default={}, description="Initialized components.")


class CacheClearResponse(BaseModel):
    deleted: int = Field(..., description="Number of evicted cache entries.")


# ── API Routes ──────────────────────────────────────────────────

@app.get(
    "/",
    summary="Service root",
    tags=["system"]
)
async def root() -> Dict[str, str]:
    """Returns a lightweight landing response for deployment health checks."""
    return {"status": "ok", "service": "IIT Mandi Chatbot RAG API"}

@app.post(
    "/api/chat",
    response_model=ChatResponse,
    summary="Ask a student support question",
    tags=["chat"]
)
@limiter.limit(settings.rate_limit_per_minute)
async def chat(
    request: Request,
    body: ChatRequest
) -> Dict[str, Any]:
    """
    Process a user query through the full RAG pipeline:
    1. Semantic Response Cache Check (Task 9)
    2. Hybrid Retrieval with Query Decomposition (Task 2)
    3. Dynamic Cross-Encoder Rerank (Task 3)
    4. Source Confidence Scoring (Task 4)
    5. Async Constrained Generation (Task 5+6+7)
    6. Response Cache Storage
    7. Telemetry & Observability Logging (Task 10)
    """
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # Greeting Interceptor
    query_clean = query.strip().lower().rstrip("!?. ")
    if query_clean in GREETINGS:
        return {
            "answer": "Hello! I'm JoSAAssist, your IIT Mandi admissions assistant. Ask me about IIT Mandi branches, JoSAA cutoffs, fees, hostel, or campus life.",
            "sources": [],
            "cached": False
        }

    logger.info("Received chat query: '%s'", query[:100])
    
    start_time = time.perf_counter()

    # 1. Semantic Response Cache Check (Task 9) - BYPASSED (No cache for RAG as per instruction)
    cached_res = None

    # 2. Rich Intent Classification
    query_info = classify_query_rich(query)
    logger.info("Rich query classification: %s", query_info)

    # 3. Hybrid Retrieval + Conditional Reranking Stage (RAG_TIMEOUT = 30.0 seconds)
    try:
        async def run_retrieval_and_reranking():
            # If the query skips reranking, retrieve more chunks (top_k=30) to provide richer synthesis depth
            retrieval_top_k = 30 if not query_info.get("needs_rerank", False) else settings.top_k
            candidates = await asyncio.to_thread(
                retriever.retrieve_with_boost, 
                query, 
                retrieval_top_k, 
                query_info
            )
            
            if query_info.get("needs_rerank", False):
                logger.info("Executing conditional rerank for query: %s", query)
                is_comparison = query_info["type"] == "comparison_query"
                top_n = 10 if is_comparison else 5
                # Cap input to cross-encoder to avoid CPU timeout (>15 pairs = slow)
                candidates_for_rerank = candidates[:15]
                reranked_chunks = await asyncio.to_thread(reranker.rerank, query, candidates_for_rerank, top_n)
            else:
                logger.info("Skipping rerank for query (boosted retrieval sufficient): %s", query)
                reranked_chunks = candidates
                
            return candidates, reranked_chunks

        candidates, reranked = await asyncio.wait_for(
            run_retrieval_and_reranking(),
            timeout=30.0
        )

    except asyncio.TimeoutError:
        logger.error("RAG retrieval/reranking timed out (budget 30.0s exceeded). Falling back to empty candidates.")
        candidates, reranked = [], []

    except Exception as e:
        logger.exception("Error during hybrid retrieval: %s", e)
        raise HTTPException(status_code=500, detail="Retrieval failed. Please try again later.")

    # 4. Source Confidence Scoring (Task 4)
    try:
        confident_chunks = confidence_scorer.score_chunks(query, reranked)
    except Exception as e:
        logger.exception("Error during confidence scoring: %s", e)
        raise HTTPException(status_code=500, detail="Confidence scoring failed. Please try again later.")

    # 5. Constrained Async Generation (Task 5 + 6 + 7)
    try:
        history_dicts = [{"role": msg.role, "content": msg.content} for msg in body.history]
        res = await generate_answer(query, confident_chunks, history=history_dicts, query_info=query_info)
    except Exception as e:
        logger.exception("Error during response generation: %s", e)
        # Graceful degradation: return informative message instead of bare 500
        return {
            "answer": (
                "I'm currently experiencing high load and response generation is temporarily unavailable. "
                "Please try again in a moment. For urgent queries, contact the IIT Mandi academic office directly."
            ),
            "sources": [],
            "cached": False
        }

    latency_ms = (time.perf_counter() - start_time) * 1000.0

    # Clean sources for formatting
    clean_sources = [
        {"index": s["index"], "source": s["source"]}
        for s in res["sources"]
    ]

    # 6. Response Cache Storage (Task 9) - BYPASSED (No cache for RAG as per instruction)
    pass

    # 7. Telemetry & Observability logging (Task 10)
    try:
        chunk_scores = [c.get("confidence_score", 0.0) for c in confident_chunks]
        log_query_event(
            query=query,
            retrieval_count=len(candidates),
            after_rerank=len(reranked),
            after_confidence_filter=len(confident_chunks),
            chunk_scores=chunk_scores,
            final_confidence=res["confidence"],
            response_ms=latency_ms,
            cache_hit=False,
            answer_length=len(res["answer"]),
            insufficient_evidence=(len(confident_chunks) == 0 or res["confidence"] < 0.4)
        )

        tel = getattr(generator, "_last_telemetry", {})
        log_telemetry(
            query=query,
            rag_claims=tel.get("rag_claims", 0),
            web_cache_hits=tel.get("web_cache_hits", 0),
            gemini_calls=tel.get("gemini_calls", 0),
            discarded_claims=tel.get("discarded_claims", 0),
            contradictions=tel.get("contradictions", 0),
            latency_ms=latency_ms
        )
    except Exception as e:
        logger.error("Error writing observability log: %s", e)

    return {
        "answer": res["answer"],
        "sources": clean_sources,
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


@app.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Check local RAG index readiness",
    tags=["system"]
)
async def ready() -> Dict[str, Any]:
    """Returns whether required local RAG index files are present."""
    checks = readiness_checks()
    status_value = "ready" if all(checks.values()) else "not_ready"
    if status_value != "ready":
        raise HTTPException(status_code=503, detail={"status": status_value, "checks": checks})
    return {"status": status_value, "checks": checks}


@app.get(
    "/api/warmup",
    response_model=WarmupResponse,
    summary="Warm up RAG components for cron keep-alive",
    tags=["system"]
)
async def warmup(
    _token: None = Depends(verify_warmup_token)
) -> Dict[str, Any]:
    """Initializes heavy RAG components; useful for scheduled keep-alive pings."""
    try:
        components = initialize_pipeline()
        return {"status": "ready", "components": components}
    except Exception as e:
        logger.exception("Warmup failed: %s", e)
        raise HTTPException(status_code=500, detail="Warmup failed. Please try again later.")


@app.delete(
    "/api/cache",
    response_model=CacheClearResponse,
    summary="Clear the response cache database",
    tags=["system"]
)
async def clear_cache(
    _token: None = Depends(verify_warmup_token)
) -> Dict[str, int]:
    """Clears all stored entries in the SQLite query cache."""
    try:
        deleted_count = cache.clear()
        return {"deleted": deleted_count}
    except Exception as e:
        logger.error("Failed to clear cache: %s", e)
        raise HTTPException(status_code=500, detail="Failed to clear cache. Please try again later.")


class CacheCleanupResponse(BaseModel):
    deleted: int = Field(..., description="Number of evicted expired cache entries.")


@app.post(
    "/api/cache/cleanup",
    response_model=CacheCleanupResponse,
    summary="Trigger cache invalidation cleanup",
    tags=["system"]
)
async def cache_cleanup(
    _token: None = Depends(verify_warmup_token)
) -> Dict[str, int]:
    """Triggers eviction of expired structured web claims from the SQLite cache."""
    try:
        deleted = cache.cleanup_expired_web_claims()
        return {"deleted": deleted}
    except Exception as e:
        logger.error("Failed to run cache cleanup: %s", e)
        raise HTTPException(status_code=500, detail="Failed to run cache cleanup. Please try again later.")
