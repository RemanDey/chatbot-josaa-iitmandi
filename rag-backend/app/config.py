"""
Application settings loaded from environment variables / .env file.
All settings are local — no paid API keys required.
"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """RAG pipeline configuration. All values can be overridden via .env file."""

    # ── Groq & OpenRouter LLMs ──────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_api_url: str = "https://api.groq.com/openai/v1/chat/completions"

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct"
    openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions"

    # ── Embedding model (HuggingFace, downloaded automatically) ─
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # ── ChromaDB & BM25 ─────────────────────────────────────────
    chroma_db_path: str = "data/chroma_db"
    chroma_collection_name: str = "iitmandi"
    bm25_pickle_file: str = "data/bm25_corpus.pkl"

    # ── RAG retrieval ───────────────────────────────────────────
    top_k: int = 5

    # ── Generation parameters ───────────────────────────────────
    temperature: float = 0.2
    max_tokens: int = 512
    num_ctx: int = 4096

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance — imported everywhere
settings = Settings()
