"""
TASK 5 + 6 + 7 — Constrained Generation + Confidence Gate + Citations (app/generator.py)

Generates answers using OpenRouter API with model nvidia/nemotron-3-super-120b-a12b:free.
Applies a confidence gate check, constructs context with source labels,
injects strict prompt instructions, parses citations, and handles API errors.

Exports:
  - `generate_answer(query: str, confident_chunks: List[Dict[str, Any]]) -> Dict[str, Any]`
  - `generator` (singleton instance of RAGGenerator)
"""

import logging
import os
from typing import List, Dict, Any

import httpx
from app.config import settings

logger = logging.getLogger("generator")

# ── Constants ───────────────────────────────────────────────────
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
DEFAULT_INSUFFICIENT_INFO_MSG = "I don't have enough information to answer this."

SYSTEM_PROMPT = """You are an IIT Mandi JOSAA Counsellor Bot.

Follow the rules below **strictly**, in order of priority. Do not violate any rule under any circumstance.

---

🟥 [RULE 1: Scope Enforcement - HIGHEST PRIORITY]
Only respond to queries that are:
- Related to JOSAA counselling
- Involving IITs (institute-specific, comparisons, preferences)
- About academic branches, college life, placements, or infrastructure

If a question is outside this scope:
- For comparison questions (e.g., A vs B), give all valid information on both A and B, if available.
- For general queries (e.g., climate or campus environment), answer as per this:
   - IIT Mandi is located in Mandi, Himachal Pradesh (near Manali), in a hilly region.
   - It is an Institute of National Importance, with no major accessibility or climate issues.
- If you still cannot answer the query, respond with this exact phrase:
   "I’m not sure based on current information. It’s best to ask a senior or refer to official resources."

---

🟧 [RULE 2: Data & Link Governance]
You may ONLY use the following links if strictly necessary:
- Placements-related:  
  https://drive.google.com/file/d/11qJSFscLzaTeCF1KOcNtyhX0gN3VUbxz/view
- Cutoff/opening-closing rank archive:  
  https://josaa.admissions.nic.in/applicant/seatmatrix/openingclosingrankarchieve.aspx

NEVER include external links unless:
- The user explicitly asks about placements or cutoffs
- Or the response is incomplete or insufficient without them

NEVER hallucinate or fabricate links. Do not suggest any source outside the provided context.

---

🟨 [RULE 3: Tone, Bias, and Comparison Handling]
- Maintain a strictly neutral, fact-based, and professional tone.
- Never be emotional, informal, overly promotional, or desperate.
- Do not use markdown, emojis, or casual phrasing.
- Avoid exaggeration or unverified claims at all times.
- Do NOT defame or mention any negative aspects of IIT Mandi, unless directly asked for a branch/institute comparison.
- When comparing colleges or branches:
   - Be fair and factual.
   - Do not fabricate pros/cons.
   - Subtly highlight IIT Mandi’s advantages when relevant:
     • Scenic location in the Himalayas  
     • Evolving research ecosystem  
     • Strong coding and development culture  
     • Improving infrastructure and academics

- Do not compare branches within the same IIT unless the user specifically asks.

---

🟩 [RULE 4: Language and Structure]
- Do not use names or refer to individuals (students, faculty, etc.)
- Do not use informal speech, jokes, emojis, or markdown.
- Keep answers detailed, general, helpful, and grounded.

---

🟪 [RULE 5: Priority to Freshness - CRITICAL]
If the context contains conflicting or differing information for the same branch, program, fee, menu, or academic rule across different sources:
- ALWAYS prioritize the most recent or latest information.
- Prefer sources mentioning newer academic years (e.g. 2025-26 over 2024-25).
- Do not mention or blend older, outdated rules or figures if newer ones are present.

---

Answer ONLY using the provided context below.
Do NOT use any external knowledge.
Do NOT assume or infer facts not present in context.
If the context does not contain enough information, say exactly:
"I don't have enough information to answer this." (Unless overridden by a specific scope refusal rule above)"""


class RAGGenerator:
    """
    RAG answer generator using Groq as primary LLM and OpenRouter as fallback.
    """

    def __init__(self):
        # Read Groq API key and configs with multiple fallbacks
        self.groq_api_key = (
            os.getenv("GROQ_API_KEY") or
            getattr(settings, "groq_api_key", None) or
            ""
        ).strip()
        self.groq_model = (
            os.getenv("GROQ_MODEL") or
            getattr(settings, "groq_model", "llama-3.3-70b-versatile")
        ).strip()
        self.groq_api_url = (
            os.getenv("GROQ_API_URL") or
            getattr(settings, "groq_api_url", "https://api.groq.com/openai/v1/chat/completions")
        ).strip()

        # Read OpenRouter API key and configs with multiple fallbacks
        self.openrouter_api_key = (
            os.getenv("OPENROUTER_API_KEY") or
            getattr(settings, "openrouter_api_key", None) or
            ""
        ).strip()
        self.openrouter_model = (
            os.getenv("OPENROUTER_MODEL") or
            getattr(settings, "openrouter_model", "meta-llama/llama-3.3-70b-instruct")
        ).strip()
        self.openrouter_api_url = (
            os.getenv("OPENROUTER_API_URL") or
            getattr(settings, "openrouter_api_url", "https://openrouter.ai/api/v1/chat/completions")
        ).strip()

    def generate_answer(self, query: str, confident_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a constrained response for the query using retrieved chunks.

        Args:
            query: The user's query string.
            confident_chunks: List of retrieved chunks that passed confidence threshold.

        Returns:
            Dictionary containing 'answer', 'sources', and 'confidence'.
        """
        query_stripped = query.strip()

        # ── Step 0: Safeguard Refusal for New Branches ──────────────────
        query_lower = query_stripped.lower()
        new_branches = [
            "quantum science", 
            "quantum technology",
            "agriculture engineering", 
            "agricultural engineering", 
            "chemical engineering and data analytics",
            "chemical engineering & data analytics"
        ]
        if any(branch in query_lower for branch in new_branches):
            logger.info("Deterministic refusal triggered for branch query: %s", query_stripped)
            return {
                "answer": "Not much information is available for this branch at the moment. It is best to ask a senior or refer to official resources.",
                "sources": [],
                "confidence": 0.0
            }

        # ── Step 1: Confidence Gate ────────────────────────────────────
        if not confident_chunks:
            logger.info("Confidence gate: No chunks provided. Returning default response.")
            return {
                "answer": DEFAULT_INSUFFICIENT_INFO_MSG,
                "sources": [],
                "confidence": 0.0
            }

        max_confidence = max(c["confidence_score"] for c in confident_chunks)
        if max_confidence < 0.4:
            logger.info("Confidence gate: Max chunk score (%.3f) is less than 0.4. Returning default response.", max_confidence)
            return {
                "answer": DEFAULT_INSUFFICIENT_INFO_MSG,
                "sources": [],
                "confidence": 0.0
            }

        # ── Step 2: Build Context String ───────────────────────────────
        context_parts = []
        for i, chunk in enumerate(confident_chunks, 1):
            source = chunk.get("metadata", {}).get("source", "unknown")
            score = chunk.get("confidence_score", 0.0)
            text = chunk.get("text", "").strip()
            
            context_parts.append(
                f"[SOURCE {i}: {source} | confidence: {score:.2f}]\n{text}"
            )
        context_string = "\n\n".join(context_parts)

        # ── Step 3: Build Prompt ───────────────────────────────────────
        prompt = (
            f"System: {SYSTEM_PROMPT}\n\n"
            f"Context:\n{context_string}\n\n"
            f"Question: {query_stripped}\n\n"
            "Answer (cite sources inline as [1], [2], etc.):"
        )

        # ── Step 4: Call LLM API (Groq primary, OpenRouter fallback) ─────
        answer = None
        groq_error = None
        openrouter_error = None

        # 1. Attempt Groq call
        if self.groq_api_key and self.groq_api_key != "your_groq_api_key_here":
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.groq_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0
            }
            logger.info("Attempting to generate answer via Groq (%s)...", self.groq_model)
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(self.groq_api_url, headers=headers, json=payload)
                    response.raise_for_status()
                    res_data = response.json()
                    
                    if "error" in res_data:
                        raise RuntimeError(f"Groq API returned error: {res_data['error']}")
                    
                    choices = res_data.get("choices", [])
                    if not choices:
                        raise RuntimeError("Empty choices in Groq response.")
                    
                    answer = choices[0].get("message", {}).get("content", "").strip()
                    logger.info("Successfully generated answer via Groq.")
            except Exception as e:
                groq_error = str(e)
                logger.warning("Groq generation failed: %s. Falling back to OpenRouter...", groq_error)
        else:
            groq_error = "Groq API Key is not configured."
            logger.warning("Groq API Key not found. Falling back directly to OpenRouter...")

        # 2. Fallback to OpenRouter
        if answer is None:
            if self.openrouter_api_key and self.openrouter_api_key != "your_openrouter_api_key_here":
                headers = {
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "https://github.com/google/antigravity",
                    "X-Title": "IIT Mandi Chatbot",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.openrouter_model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0
                }
                logger.info("Attempting to generate answer via OpenRouter fallback (%s)...", self.openrouter_model)
                try:
                    with httpx.Client(timeout=30.0) as client:
                        response = client.post(self.openrouter_api_url, headers=headers, json=payload)
                        response.raise_for_status()
                        res_data = response.json()
                        
                        if "error" in res_data:
                            raise RuntimeError(f"OpenRouter API returned error: {res_data['error']}")
                        
                        choices = res_data.get("choices", [])
                        if not choices:
                            raise RuntimeError("Empty choices in OpenRouter response.")
                        
                        answer = choices[0].get("message", {}).get("content", "").strip()
                        logger.info("Successfully generated answer via OpenRouter fallback.")
                except Exception as e:
                    openrouter_error = str(e)
                    logger.critical("OpenRouter fallback also failed: %s", openrouter_error)
            else:
                openrouter_error = "OpenRouter API Key is not configured."
                logger.critical("OpenRouter API Key not found and Groq failed!")

        # 3. If both failed, raise RuntimeError
        if answer is None:
            raise RuntimeError(
                f"Failed to generate answer from both Groq and OpenRouter:\n"
                f"- Groq error: {groq_error}\n"
                f"- OpenRouter error: {openrouter_error}"
            )

        # ── Step 5: Build Citations List ───────────────────────────────
        sources = [
            {
                "index": i + 1,
                "source": chunk.get("metadata", {}).get("source", "unknown"),
                "confidence": float(chunk.get("confidence_score", 0.0))
            }
            for i, chunk in enumerate(confident_chunks)
        ]

        logger.info("Successfully generated answer. Length = %d.", len(answer))

        return {
            "answer": answer,
            "sources": sources,
            "confidence": float(max_confidence)
        }


# Singleton instance
generator = RAGGenerator()


# Direct function export for ease of import
def generate_answer(query: str, confident_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generates an answer using the singleton generator."""
    return generator.generate_answer(query, confident_chunks)
