#!/usr/bin/env python3
"""
TASK 8 — Continuous Evals (evals/run_eval.py)

Loads test queries from evals/test_queries.jsonl, executes the full RAG pipeline,
checks if expected keywords appear in the generated answer, computes metrics
(Retrieval Hit Rate, Hallucination Flag Rate, and No Answer Rate),
prints a nice summary table, and saves results to evals/results.json.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import logging
# Minimal logging for clean output during evaluations
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("evals")

from app.retriever import retriever
from app.reranker import reranker
from app.confidence import confidence_scorer
from app.generator import generate_answer

# ── Helper Functions ────────────────────────────────────────────

def check_keywords_in_text(text: str, keywords: List[str]) -> bool:
    """Check if any of the expected keywords appear in the text (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def get_content_words(text: str) -> set:
    """
    Extract significant content words from text for simple hallucination check.
    Excludes punctuation, small words, and common English stop words.
    """
    # Find all words with length >= 4 characters
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    
    # Common stopwords to exclude from content checking
    stopwords = {
        "what", "where", "when", "your", "that", "this", "with", "from",
        "they", "have", "been", "were", "will", "would", "should", "could",
        "their", "there", "about", "which", "than", "them", "then", "some",
        "more", "other", "under", "over", "into", "onto", "through", "during",
        "about", "these", "those", "here", "there", "each", "both", "either",
        "neither", "some", "many", "such"
    }
    return {w for w in words if w not in stopwords}


def check_hallucination(answer: str, retrieved_chunks: List[Dict[str, Any]]) -> bool:
    """
    Check if the answer contains content words that are completely absent
    from the retrieved chunks (heuristic/proxy).
    """
    # If the answer indicates insufficient evidence, it is not a hallucination
    if "don't have enough information" in answer.lower():
        return False
        
    answer_words = get_content_words(answer)
    if not answer_words:
        return False
        
    chunk_words = set()
    for chunk in retrieved_chunks:
        chunk_words.update(get_content_words(chunk.get("text", "")))
        
    # Find words in answer not found in any chunk
    hallucinated_words = answer_words - chunk_words
    
    # If more than 2 significant content words are completely missing, flag it
    return len(hallucinated_words) > 2


def run_evaluation() -> None:
    test_queries_file = PROJECT_ROOT / "evals" / "test_queries.jsonl"
    results_file = PROJECT_ROOT / "evals" / "results.json"
    
    if not test_queries_file.exists():
        print(f"Error: Test queries file not found at {test_queries_file}")
        sys.exit(1)
        
    print(f"=== Starting RAG Evaluation ===")
    print(f"Loading queries from: {test_queries_file.name}")
    
    queries_data = []
    with open(test_queries_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                queries_data.append(json.loads(line))
                
    total_queries = len(queries_data)
    print(f"Loaded {total_queries} queries for evaluation.\n")
    
    eval_results = []
    retrieval_hits = 0
    hallucinations = 0
    no_answers = 0
    total_time_ms = 0.0
    
    print(f"{'#':<3} | {'Query':<50} | {'Hit?':<5} | {'Halluc?':<7} | {'No Ans?':<7} | {'Time (ms)':<9}")
    print("-" * 95)
    
    for idx, item in enumerate(queries_data, 1):
        query = item["query"]
        expected_keywords = item["expected_keywords"]
        
        start_time = time.perf_counter()
        
        # 1. Retrieve candidates
        candidates = retriever.retrieve(query, top_k=20)
        
        # 2. Rerank
        reranked = reranker.rerank(query, candidates, top_n=5)
        
        # 3. Confidence score
        confident = confidence_scorer.score_chunks(query, reranked)
        
        # 4. Generate answer
        result = generate_answer(query, confident)
        
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000.0
        total_time_ms += duration_ms
        
        # Calculate retrieval hit rate based on top 5 reranked chunks
        has_hit = False
        if reranked:
            # Check if any of the top 5 reranked chunks contains any of the expected keywords
            for c in reranked[:5]:
                if check_keywords_in_text(c["text"], expected_keywords):
                    has_hit = True
                    break
        if has_hit:
            retrieval_hits += 1
            
        # Check hallucination
        is_hallucinated = check_hallucination(result["answer"], reranked)
        if is_hallucinated:
            hallucinations += 1
            
        # Check no-answer rate
        is_no_answer = "don't have enough information" in result["answer"].lower()
        if is_no_answer:
            no_answers += 1
            
        # Truncate query for display
        query_display = query[:47] + "..." if len(query) > 50 else query
        
        print(f"{idx:<3} | {query_display:<50} | {str(has_hit):<5} | {str(is_hallucinated):<7} | {str(is_no_answer):<7} | {duration_ms:<9.1f}")
        
        eval_results.append({
            "query": query,
            "expected_keywords": expected_keywords,
            "answer": result["answer"],
            "confidence": result["confidence"],
            "duration_ms": duration_ms,
            "retrieval_hit": has_hit,
            "hallucinated": is_hallucinated,
            "no_answer": is_no_answer
        })
        
    # Compute aggregates
    hit_rate = (retrieval_hits / total_queries) * 100.0 if total_queries > 0 else 0.0
    hallucination_rate = (hallucinations / total_queries) * 100.0 if total_queries > 0 else 0.0
    no_answer_rate = (no_answers / total_queries) * 100.0 if total_queries > 0 else 0.0
    avg_latency = total_time_ms / total_queries if total_queries > 0 else 0.0
    
    print("\n" + "=" * 50)
    print("                EVALUATION SUMMARY")
    print("=" * 50)
    print(f"Total Queries evaluated : {total_queries}")
    print(f"Retrieval Hit Rate (top 5) : {hit_rate:.1f}%")
    print(f"Hallucination Flag Rate  : {hallucination_rate:.1f}%")
    print(f"No Answer Rate           : {no_answer_rate:.1f}%")
    print(f"Average Latency (ms)     : {avg_latency:.1f} ms")
    print("=" * 50 + "\n")
    
    # Save to results.json
    output_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_queries": total_queries,
            "retrieval_hit_rate": hit_rate,
            "hallucination_rate": hallucination_rate,
            "no_answer_rate": no_answer_rate,
            "average_latency_ms": avg_latency
        },
        "details": eval_results
    }
    
    os.makedirs(results_file.parent, exist_ok=True)
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
        
    print(f"Results saved to: {results_file}")


if __name__ == "__main__":
    run_evaluation()
