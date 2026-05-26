---
title: IIT Mandi Chatbot API
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# IIT Mandi Student Support Chatbot — RAG API Backend

A highly optimized, zero-hallucination Retrieval-Augmented Generation (RAG) backend designed to answer student support queries for IIT Mandi. It combines **Dense Retrieval (ChromaDB)** and **Sparse Retrieval (BM25)** using **Reciprocal Rank Fusion (RRF)**, reranked by a local **Cross-Encoder**, scored by a **Confidence Gate**, and generated using a double-failover LLM pipeline (Groq → OpenRouter) with Gemini-powered contextual enrichment.

---

## 📂 Project Directory Structure

```text
iitmandi-bot/
├── app/                  # Main application package
│   ├── __init__.py       # Package entry & warning suppressions
│   ├── cache.py          # SQLite response caching layer
│   ├── confidence.py     # Context heuristic confidence scoring
│   ├── config.py         # App configuration & settings
│   ├── generator.py      # LLM answer generator (Groq & OpenRouter failover)
│   ├── ingest.py         # Document parser, chunker & database builder
│   ├── main.py           # FastAPI server endpoints & lifespan setup
│   ├── observe.py        # Telemetry & query observability logging
│   ├── reranker.py       # Cross-Encoder candidate re-scoring
│   └── retriever.py      # Hybrid RRF (Vector + BM25) retriever
├── data/                 # Data storage folder (raw KB docs kept; generated indexes rebuilt at build time)
│   ├── raw/              # Raw knowledge-base sources
│   │   ├── chat/         # Cleaned chat transcripts (QA pairs)
│   │   ├── doc/          # Official handbooks, policies, and PDFs
│   │   ├── faq/          # FAQ sheets (.txt, .md)
│   │   └── web/          # Scraped webpages (.md, .txt)
│   ├── chroma_db/        # Persisted vector database chunks [Generated]
│   └── bm25_corpus.pkl   # Persisted BM25 keyword index [Generated]
├── evals/                # Continuous evaluation & test suites
│   ├── test_rag.py       # Unit tests for the pipeline components
│   ├── test_queries.jsonl# Benchmark evaluation query suite
│   └── run_eval.py       # Hits, hallucination, and fallback evaluations
├── logs/                 # Telemetry logs directory [Generated]
├── .env.example          # Sample environment key configuration
├── .gitignore            # Git exclusion filters
├── requirements.txt      # Python dependencies
├── run.py                # Wrapper to start development server
└── README.md             # Project documentation
```

---

## ⚙️ Installation & Configuration

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/RemanDey/chatbot-josaa-iitmandi.git
cd chatbot-josaa-iitmandi

# Create python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Environment Keys

Create a `.env` file by copying the example template:

```bash
cp .env.example .env
```

Open `.env` and fill in your API credentials:

```env
# Gemini (secondary context enrichment via Google Search)
GEMINI_API_KEY=your_gemini_api_key_here

# Primary LLM (Groq)
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Fallback LLM (OpenRouter)
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct

# Embedding model (auto-downloaded from HuggingFace, no key needed)
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
HF_TOKEN=your_huggingface_token_here

# API Authentication (Bearer token for /api/chat)
API_KEY=your_secret_password_here

# Database paths
CHROMA_DB_PATH=data/chroma_db
CHROMA_COLLECTION_NAME=iitmandi
BM25_PICKLE_FILE=data/bm25_corpus.pkl

# Retrieval config
TOP_K=20

# Runtime
APP_ENV=development
EAGER_LOAD_MODELS=true
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
WARMUP_TOKEN=
```

---

## 🗄️ Creating & Rebuilding the Databases

### 1. Organize raw data

Place files under `data/raw/` in their respective subdirectories based on content type:

| Subdirectory | Content Type | Supported Formats |
|---|---|---|
| `chat/` | Chat transcripts & QA pairs | `.jsonl` (each line: `{"instruction": "...", "response": "..."}`) |
| `doc/` | Official handbooks, policies | `.pdf`, `.txt`, `.md`, `.docx` |
| `faq/` | FAQ sheets | `.txt`, `.md` |
| `web/` | Scraped webpages | `.md`, `.txt` |

### 2. Clean rebuild (optional)

Only if you want a 100% clean rebuild — delete old generated files:

```bash
rm -rf data/chroma_db data/bm25_corpus.pkl data/doc_hashes.json data/cache.db
```

### 3. Run Ingestion

```bash
python -m app.ingest --folder data/raw
```

This will:
- Recursively parse and hash all text files
- Compute local BGE embeddings (`BAAI/bge-base-en-v1.5`, 768 dimensions)
- Build the ChromaDB vector collection
- Compile the BM25 lexical index

For the Docker image used by Hugging Face Spaces, this ingestion step is executed during image build so the generated indexes do not need to be committed to git.

> **Note:** Ingestion takes ~13 minutes on CPU for ~5800 chunks. On GPU it completes in under 2 minutes.

---

## 🚀 Running the Server

### Development (with hot-reload)

```bash
python run.py
```

The server starts at **`http://127.0.0.1:8000`**.

> **Note:** `run.py` configures Uvicorn to only watch `app/` for changes, preventing database writes or log updates from triggering infinite reload loops.

### Production (Docker)

```bash
docker build -t josaa-chatbot-backend .
docker run --env-file .env -e PORT=8000 -p 8000:8000 josaa-chatbot-backend
```

Or with Docker Compose:

```bash
docker compose up --build
```

---

## 🔑 API Authentication

All `/api/chat` requests require a **Bearer token** matching the `API_KEY` in your `.env`:

```
Authorization: Bearer your_secret_password_here
```

If `API_KEY` is left empty in `.env`, the server runs in **open mode** (no authentication required).

---

## 🌐 API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/chat` | ✅ Bearer | Main RAG chat pipeline |
| `GET` | `/health` | ❌ | Lightweight health check |
| `GET` | `/ready` | ❌ | Verifies RAG index files exist |
| `GET` | `/api/warmup?token=...` | ❌ | Pre-loads models (for cron keep-alive) |
| `DELETE` | `/api/cache` | ❌ | Clears the response cache |

### `POST /api/chat` — Request & Response

**Request Body:**

```json
{
  "query": "What branches can I get at 5000 JEE Advanced rank?",
  "history": []
}
```

**Response (200 OK):**

```json
{
  "answer": "With a JEE Advanced rank of 5000, you can get into CSE, EE, ME, and Data Science at IIT Mandi...",
  "sources": [
    { "index": 1, "source": "official_iitmandi_data.md" },
    { "index": 2, "source": "josaa_counselling_guide.md" }
  ],
  "cached": false
}
```

### Quick Test with cURL

```bash
curl -X POST \
  'http://127.0.0.1:8000/api/chat' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer your_secret_password_here' \
  -d '{"query": "tell me about iit mandi placements", "history": []}'
```

---

## 🧪 Testing

### Interactive Swagger UI

Once the server is running, open:
👉 **`http://127.0.0.1:8000/docs`**

1. Click the **Authorize** button (top-right)
2. Enter your `API_KEY` value as the Bearer token
3. Expand `POST /api/chat`, click **Try it out**, enter a query, and hit **Execute**

### Unit Tests

```bash
python -m unittest evals/test_rag.py
```

### Evaluation Suite

Run benchmark checks evaluating retrieval hit rates and hallucination counts:

```bash
python evals/run_eval.py
```

---

## ☁️ HuggingFace Spaces Deployment

The project is deployed at: **https://aryanraj1092-iitmandi-bot.hf.space**

1. Push the repo to your HuggingFace Space (with Docker SDK).
2. Add these **Secrets** in the HF Space Settings:
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
   - `OPENROUTER_API_KEY`
   - `HF_TOKEN`
   - `API_KEY`
3. Add these **Variables**:
   - `EMBEDDING_MODEL=BAAI/bge-base-en-v1.5`
   - `TOP_K=20`
   - `EAGER_LOAD_MODELS=true`
   - `CHROMA_DB_PATH=data/chroma_db`
   - `BM25_PICKLE_FILE=data/bm25_corpus.pkl`
4. Ensure compiled index files are committed:
   - `data/chroma_db/`
   - `data/bm25_corpus.pkl`
5. After deploy, verify:

```bash
curl https://aryanraj1092-iitmandi-bot.hf.space/health
curl https://aryanraj1092-iitmandi-bot.hf.space/ready
```

---

## 📋 Render Deployment (Alternative)

This repo includes `Dockerfile`, `.dockerignore`, `docker-compose.yml`, and `render.yaml` for GitHub-based Render deployment.

1. Push the repo to GitHub.
2. In Render, create a new Blueprint from this repo. Render will read `render.yaml`.
3. Add these secret environment variables in the Render dashboard:
   - `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `HF_TOKEN`, `API_KEY`
4. Keep these non-secret values from `render.yaml`:
   - `EAGER_LOAD_MODELS=false`
   - `CORS_ALLOWED_ORIGINS=https://chatbot-josaa-iitmandi.onrender.com`
5. After deploy, test:

```bash
curl https://YOUR-SERVICE.onrender.com/health
curl https://YOUR-SERVICE.onrender.com/ready
```

> **Note:** If Render shows out-of-memory errors while loading `sentence-transformers`, upgrade from Free to Starter plan. The app loads local embedding and reranking models which need ~1.5 GB RAM.
