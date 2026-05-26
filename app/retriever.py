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


class SafeChromaWrapper:
    """
    A protected wrapper around ChromaDB collection to prevent any write or update operations
    at runtime. Delegates all read-only methods (like query, count) to the underlying collection.
    """
    def __init__(self, collection):
        self._collection = collection

    def add(self, *args, **kwargs):
        raise RuntimeError("Runtime pipeline cannot modify RAG DB")

    def upsert(self, *args, **kwargs):
        raise RuntimeError("Runtime pipeline cannot modify RAG DB")

    def modify(self, *args, **kwargs):
        raise RuntimeError("Runtime pipeline cannot modify RAG DB")

    def update(self, *args, **kwargs):
        raise RuntimeError("Runtime pipeline cannot modify RAG DB")

    def delete(self, *args, **kwargs):
        raise RuntimeError("Runtime pipeline cannot modify RAG DB")

    def __getattr__(self, name):
        return getattr(self._collection, name)


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
        raw_collection = self.chroma_client.get_collection(name=settings.chroma_collection_name)
        self.collection = SafeChromaWrapper(raw_collection)
        
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

    def retrieve(self, query: str, top_k: int = 20, intent: str = "general") -> List[Dict[str, Any]]:
        """
        Perform hybrid retrieval combining ChromaDB and BM25 using RRF.

        Args:
            query: User's raw question string.
            top_k: Number of candidate documents to return.
            intent: Query category to route (cutoff, placement, or general)

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

        # Query ChromaDB — use top_k directly (retrieve_with_boost already passes top_k*2)
        vector_res = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(self.collection.count(), 1)),
            include=["documents", "metadatas", "distances"]
        )

        vector_docs = vector_res.get("documents", [[]])[0]
        vector_metas = vector_res.get("metadatas", [[]])[0]
        vector_distances = vector_res.get("distances", [[]])[0]

        # Convert distance to cosine similarity score: score = 1.0 - (dist / 2.0)
        vector_ranked = []
        for doc, meta, dist in zip(vector_docs, vector_metas, vector_distances):
            score = 1.0 - (dist / 2.0)
            
            # Apply intent boost
            source_lower = meta.get("source", "").lower()
            boost = 0.0
            if intent == "placement" and any(k in source_lower for k in ["cnp", "placement", "brochure", "comparison"]):
                boost = 0.25
            elif intent == "cutoff" and any(k in source_lower for k in ["josaa", "cutoff", "counselling", "comparison"]):
                boost = 0.25
                
            vector_ranked.append({
                "text": doc,
                "metadata": meta,
                "vector_score": float(score + boost)
            })

        # ── Step 2: BM25 Search ───────────────────────────────────────
        tokenized_query = query_stripped.lower().split()
        bm25_scores = self.bm25.get_scores(tokenized_query)
        
        max_bm25_score = max(bm25_scores) if len(bm25_scores) > 0 else 0.0

        bm25_ranked = []
        # Zip BM25 scores with corpus docs and sort
        all_bm25 = []
        for doc, score in zip(self.bm25_corpus, bm25_scores):
            normalized_score = float(score / max_bm25_score) if max_bm25_score > 0.0 else 0.0
            
            # Apply intent boost
            source_lower = doc.get("metadata", {}).get("source", "").lower()
            boost = 0.0
            if intent == "placement" and any(k in source_lower for k in ["cnp", "placement", "brochure", "comparison"]):
                boost = 0.25
            elif intent == "cutoff" and any(k in source_lower for k in ["josaa", "cutoff", "counselling", "comparison"]):
                boost = 0.25
                
            all_bm25.append((doc, normalized_score + boost))
        
        all_bm25_sorted = sorted(all_bm25, key=lambda x: x[1], reverse=True)[:top_k]

        for doc, score in all_bm25_sorted:
            bm25_ranked.append({
                "text": doc["text"],
                "metadata": doc["metadata"],
                "bm25_score": score
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

    def retrieve_with_boost(self, query: str, top_k: int = 10, 
                            query_info: dict = None) -> List[Dict[str, Any]]:
        """
        Retrieves documents using RRF and applies smart category/entity metadata boosting
        based on rich query classification.
        """
        self.ensure_initialized()
        if not query_info:
            return self.retrieve(query, top_k=top_k)
            
        candidates = self.retrieve(query, top_k=top_k * 2)
        
        branch_files = ["cse.md", "ee.md", "me.md", "ce.md", "ep.md", "dse.md", "mnc.md"]
        priority_categories = query_info.get("priority_categories", [])
        entities = query_info.get("entities", [])
        query_type = query_info.get("type", "general")
        
        boosted_candidates = []
        for doc in candidates:
            boost = 0.0
            source = doc["metadata"].get("source", "").lower()
            
            # Category boost — match source filename against priority categories
            for cat in priority_categories:
                if cat == 'branch_profile' and any(b in source for b in branch_files):
                    boost += 0.3
                if cat == 'placements' and 'placement' in source:
                    boost += 0.3
                if cat == 'cutoffs' and ('cutoff' in source or 'josaa' in source):
                    boost += 0.3
                if cat == 'comparison' and 'comparison' in source:
                    boost += 0.25
                if cat == 'josaa' and ('josaa' in source or 'counselling' in source):
                    boost += 0.25
                if cat == 'admin' and 'fee' in source:
                    boost += 0.2
                if cat == 'campus' and ('hostel' in source or 'campus' in source):
                    boost += 0.2
                    
            # Entity boost
            for entity in entities:
                entity_short = entity.replace('IIT Mandi ', '').lower()
                if entity_short in source:
                    boost += 0.25
                    
            # Demote admin/fee/hostel for non-admin queries
            if query_type not in ['campus_life', 'fee_query']:
                if any(kw in source for kw in ['fee_structure', 'hostel_rules', 'fees_faq']):
                    boost -= 0.5
                    
            doc["metadata_boost"] = boost
            doc["boosted_score"] = doc["rrf_score"] + boost
            boosted_candidates.append(doc)
            
        # Re-sort candidates by boosted_score descending
        boosted_candidates.sort(key=lambda x: x["boosted_score"], reverse=True)
        
        logger.info("Retrieved and boosted %d documents for query: %s", len(boosted_candidates[:top_k]), query)
        return boosted_candidates[:top_k]


# Singleton instance exported for use
retriever = HybridRetriever()
