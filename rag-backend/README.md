# IIT Mandi Student Support Chatbot — RAG API Backend

A highly optimized, zero-hallucination Retrieval-Augmented Generation (RAG) backend designed to answer student support queries for IIT Mandi. It combines **Dense Retrieval (ChromaDB)** and **Sparse Retrieval (BM25)** using **Reciprocal Rank Fusion (RRF)**, reranked by a local **Cross-Encoder**, scored by a **Confidence Gate**, and generated using a double-failover LLM pipeline.

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
├── data/                 # Data storage folder (Git ignored except raw/)
│   ├── raw/              # Raw knowledge-base sources
│   │   ├── chat/         # Cleaning chat transcripts (QA pairs)
│   │   ├── doc/          # Official handbooks, policies, and PDFs
│   │   ├── faq/          # FAQs sheets (.txt, .md)
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
# Clone the repository and navigate inside
cd iitmandi-bot

# Initialize python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Environment Keys
Create a `.env` file in the project root by copying the example template:
```bash
cp .env.example .env
```
Open `.env` and fill in your API credentials:
```env
# Primary LLM API Key (Groq)
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Fallback LLM API Key (OpenRouter)
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct

# Local Paths & Database Config
CHROMA_DB_PATH=data/chroma_db
CHROMA_COLLECTION_NAME=iitmandi
BM25_PICKLE_FILE=data/bm25_corpus.pkl

TOP_K=5
```

---

## 🗄️ Creating & Rebuilding the Databases

To populate or rebuild the vector (ChromaDB) and lexical (BM25) indexes from scratch:

1. **Organize raw data**: Place files under `data/raw/` in their respective subdirectories based on content types (`chat/`, `doc/`, `faq/`, `web/`). Supported formats: `.pdf` (PyMuPDF), `.txt`, `.md`, `.jsonl` (each line structured as `{"instruction": "...", "response": "..."}`).

2. **Clean up old database files** (Only if you want to perform a 100% clean rebuild):
   ```bash
   rm -rf data/chroma_db data/bm25_corpus.pkl data/cache.db
   ```

3. **Run Ingestion**:
   ```bash
   python app/ingest.py --folder data/raw/
   ```
   *This recursively processes and hashes all text files, computes local BGE embeddings (`BAAI/bge-small-en-v1.5`), builds the ChromaDB collection, and compiles the BM25 index.*

---

## 🚀 Running the FastAPI Server

To launch the FastAPI server in development/reload mode:
```bash
python run.py
```
> [!NOTE]
> Running the server through `run.py` ensures that hot-reloading **only** watches the `app/` directory. This prevents active database cache updates (`data/cache.db`) or log writes (`logs/rag.log`) from triggering infinite server reload loops.

The server binds to **`http://127.0.0.1:8000`**.

---

## 🌐 Testing & Interactive Swagger UI

1. **Interactive UI**: Once the server starts, open your browser and navigate to:
   👉 **`http://127.0.0.1:8000/docs`**
   *Here you can visually test `/api/chat` by typing query inputs and inspecting live responses, inline citations, and confidence scores.*

2. **Run Unit Tests**: To execute unit tests validating LLM failovers, caching, and retrieval configurations:
   ```bash
   python -m unittest evals/test_rag.py
   ```

3. **Run Evaluation Suite**: To run benchmark query checks evaluating retrieval hit rates and hallucination counts:
   ```bash
   python evals/run_eval.py
   ```
