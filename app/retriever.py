"""
TASK 2 — Hybrid Retrieval (app/retriever.py)

Implements BM25 + vector search combined using Reciprocal Rank Fusion (RRF).
Exports:
  - `HybridRetriever` class with `retrieve(query, top_k)` method.
"""

import logging
import os
import pickle
import sys
from pathlib import Path
from typing import List, Dict, Any

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger("retriever")


class HybridRetriever:
    """
    Handles combined vector (ChromaDB) and lexical (BM25) search
    using Reciprocal Rank Fusion (RRF).
    """

    def __init__(self):
        self.embedding_model = None
        self.chroma_client = None
        self.collection = None
        self.bm25 = None
        self.bm25_corpus = []
        self._initialized = False

    def ensure_initialized(self) -> None:
        """Lazy-initialize heavy models and databases."""
        if self._initialized:
            return

        logger.info("Initializing HybridRetriever...")
        
        # 1. Load ChromaDB collection
        chroma_path = settings.chroma_db_path
        if not os.path.exists(chroma_path):
            raise FileNotFoundError(f"ChromaDB directory not found at {chroma_path}. Run ingest first.")
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.chroma_client.get_collection(name=settings.chroma_collection_name)
        
        # 2. Load BM25 index
        bm25_path = settings.bm25_pickle_file
        if not os.path.exists(bm25_path):
            raise FileNotFoundError(f"BM25 index file not found at {bm25_path}. Run ingest first.")
        with open(bm25_path, "rb") as f:
            bm25_data = pickle.load(f)
            self.bm25_corpus = bm25_data["corpus"]
            tokenized_corpus = bm25_data["tokenized_corpus"]
            
        logger.info("Loading BM25 index with %d documents.", len(self.bm25_corpus))
        self.bm25 = BM25Okapi(tokenized_corpus)
        
        # 3. Load Embedding Model
        logger.info("Loading embedding model: %s", settings.embedding_model)
        self.embedding_model = SentenceTransformer(settings.embedding_model)
        
        self._initialized = True
        logger.info("HybridRetriever initialized successfully.")

    def retrieve(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Perform hybrid retrieval combining ChromaDB and BM25 using RRF.

        Args:
            query: User's raw question string.
            top_k: Number of candidate documents to return.

        Returns:
            List of dictionaries containing 'text', 'metadata', 'vector_score',
            'bm25_score', and 'rrf_score' sorted by rrf_score descending.
        """
        self.ensure_initialized()
        query_stripped = query.strip()
        if not query_stripped:
            return []

        # ── Step 1: Vector Search ─────────────────────────────────────
        # Embed query
        query_embedding = self.embedding_model.encode(
            query_stripped, normalize_embeddings=True
        ).tolist()

        # Query ChromaDB
        vector_res = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k * 2, self.collection.count()),  # Retrieve plenty of candidates
            include=["documents", "metadatas", "distances"]
        )

        vector_docs = vector_res.get("documents", [[]])[0]
        vector_metas = vector_res.get("metadatas", [[]])[0]
        vector_distances = vector_res.get("distances", [[]])[0]

        # Convert distance to cosine similarity score: score = 1 / (1 + distance)
        vector_ranked = []
        for doc, meta, dist in zip(vector_docs, vector_metas, vector_distances):
            score = 1.0 / (1.0 + dist)
            vector_ranked.append({
                "text": doc,
                "metadata": meta,
                "vector_score": float(score)
            })

        # ── Step 2: BM25 Search ───────────────────────────────────────
        tokenized_query = query_stripped.lower().split()
        bm25_scores = self.bm25.get_scores(tokenized_query)
        
        max_bm25_score = max(bm25_scores) if len(bm25_scores) > 0 else 0.0

        bm25_ranked = []
        # Zip BM25 scores with corpus docs and sort
        all_bm25 = []
        for doc, score in zip(self.bm25_corpus, bm25_scores):
            all_bm25.append((doc, score))
        
        all_bm25_sorted = sorted(all_bm25, key=lambda x: x[1], reverse=True)[:top_k * 2]

        for doc, score in all_bm25_sorted:
            normalized_score = float(score / max_bm25_score) if max_bm25_score > 0.0 else 0.0
            bm25_ranked.append({
                "text": doc["text"],
                "metadata": doc["metadata"],
                "bm25_score": normalized_score
            })

        # ── Step 3: Reciprocal Rank Fusion (RRF) ──────────────────────
        # RRF constant k = 60
        RRF_K = 60.0
        rrf_registry = {}

        # Rank documents from vector search
        for rank, item in enumerate(vector_ranked[:top_k], 1):
            text = item["text"]
            if text not in rrf_registry:
                rrf_registry[text] = {
                    "text": text,
                    "metadata": item["metadata"],
                    "vector_score": item["vector_score"],
                    "bm25_score": 0.0,
                    "rrf_score": 0.0
                }
            rrf_registry[text]["rrf_score"] += 1.0 / (RRF_K + rank)

        # Rank documents from BM25 search
        for rank, item in enumerate(bm25_ranked[:top_k], 1):
            text = item["text"]
            if text not in rrf_registry:
                rrf_registry[text] = {
                    "text": text,
                    "metadata": item["metadata"],
                    "vector_score": 0.0,
                    "bm25_score": item["bm25_score"],
                    "rrf_score": 0.0
                }
            else:
                rrf_registry[text]["bm25_score"] = item["bm25_score"]
            rrf_registry[text]["rrf_score"] += 1.0 / (RRF_K + rank)

        # Sort the fused candidates by RRF score descending
        fused_candidates = list(rrf_registry.values())
        fused_candidates.sort(key=lambda x: x["rrf_score"], reverse=True)

        return fused_candidates[:top_k]


# Singleton instance exported for use
retriever = HybridRetriever()
