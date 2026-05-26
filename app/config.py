"""
Application settings loaded from environment variables / .env file.
All settings are local — no paid API keys required.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """RAG pipeline configuration. All values can be overridden via .env file."""

    # ── Runtime / deployment ────────────────────────────────────
    app_env: str = "development"
    eager_load_models: bool = True
    warmup_token: str = ""
    api_key: str = ""
    rate_limit_per_minute: str = "25/minute"
    cors_allowed_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://chatbot-josaa-iitmandi.onrender.com"
    )

    # ── Groq & OpenRouter & Gemini LLMs ──────────────────────────────────
    gemini_api_key: str = ""
    gemini_second_api_key: str = ""
    gemini_third_api_key: str = ""
    
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_api_url: str = "https://api.groq.com/openai/v1/chat/completions"

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct"
    openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions"

    deepseek_api_key: str = ""
    deepseek_api_url: str = "https://api.deepseek.com/v1/chat/completions"
    deepseek_model: str = "deepseek-chat"

    nvidia_api_key: str = ""
    nvidia_api_url: str = "https://integrate.api.nvidia.com/v1/chat/completions"
    nvidia_model: str = "meta/llama-3.3-70b-instruct"

    hf_api_key: str = ""
    hf_api_url: str = "https://router.huggingface.co/v1/chat/completions"
    hf_model: str = "meta-llama/Llama-3.3-70B-Instruct"

    # ── Embedding model (HuggingFace, downloaded automatically) ─
    embedding_model: str = "BAAI/bge-base-en-v1.5"

    # ── ChromaDB & BM25 ─────────────────────────────────────────
    chroma_db_path: str = "data/chroma_db"
    chroma_collection_name: str = "iitmandi"
    bm25_pickle_file: str = "data/bm25_corpus.pkl"

    # ── RAG retrieval ───────────────────────────────────────────
    top_k: int = 20

    # ── Generation parameters ───────────────────────────────────
    temperature: float = 0.3
    max_tokens: int = 1024
    num_ctx: int = 4096

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def cors_origins(self) -> list[str]:
        """Return comma-separated CORS origins as a clean list."""
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


# Singleton instance — imported everywhere
settings = Settings()
