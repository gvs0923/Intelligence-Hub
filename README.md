# Engineering Intelligence Hub

A fully local RAG (Retrieval-Augmented Generation) system that lets engineering teams ingest their codebases, documentation, and incident reports — then query everything with natural language.

No cloud APIs, no data leaves your machine. Runs entirely on Ollama for LLM and embeddings.

## What It Does

1. **Ingest** — Point it at a Git repo, a folder of Markdown docs, or incident logs. It reads, parses, and chunks the content intelligently (AST-aware chunking for code, semantic splitting for prose).
2. **Index** — Chunks are embedded into vectors (Ollama / sentence-transformers) and stored in ChromaDB, with a parallel BM25 sparse index for keyword matching.
3. **Retrieve** — Hybrid retrieval combines dense (vector) and sparse (BM25) results using Reciprocal Rank Fusion for better recall than either alone.
4. **Generate** — The top-k relevant chunks are fed as context to a local LLM to produce grounded, source-cited answers.
5. **Query** — Ask questions through a REST API or a Streamlit UI.

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| LLM & Embeddings | Ollama (llama3.2, nomic-embed-text) |
| Vector Store | ChromaDB |
| Sparse Index | BM25 (rank-bm25) |
| Code Parsing | tree-sitter |
| Database | SQLite + SQLAlchemy 2.0 |
| Task Queue | Celery + Redis |
| UI | Streamlit |
| Logging | structlog |
| Package Manager | uv |

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/gvs0923/Intelligence-Hub.git
cd Intelligence-Hub

# 2. Copy env file
cp .env.example .env

# 3. Run with Docker (starts app + Ollama + Redis)
docker compose up --build

# 4. Or run locally
uv sync
uv run uvicorn src.api.main:app --reload
```

Health check: `GET http://localhost:8000/health`

## Project Structure

```
src/
├── api/           # FastAPI app, routes, middleware, request/response models
├── config.py      # Centralised configuration (Pydantic Settings)
├── db/            # SQLAlchemy ORM models & session management
├── ingestion/     # Data source ingesters & chunking strategies
├── indexing/      # Embedding providers
├── retrieval/     # Dense, sparse, and hybrid retrievers
├── generation/    # LLM prompt & generation layer
├── ui/            # Streamlit front-end
└── logging_config.py
```

