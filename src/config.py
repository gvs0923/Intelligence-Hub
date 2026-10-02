from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # --- App ---
    app_name: str = "Engineering Intelligence Hub"
    environment: str = "development"  # development | production
    log_level: str = "INFO"

    # --- Ollama (LLM + embeddings) ---
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # --- Fallback embedder (if Ollama is down) ---
    fallback_embedding_model: str = "all-MiniLM-L6-v2"
    fallback_embedding_dim: int = 384

    # --- Chunking ---
    chunk_size: int = 512
    chunk_overlap: int = 50
    max_code_chunk_lines: int = 150

    # --- Retrieval ---
    top_k_dense: int = 20
    top_k_bm25: int = 20
    top_k_final: int = 5
    rrf_k: int = 60  # Reciprocal Rank Fusion constant
    min_confidence_threshold: float = 0.3

    # --- Storage paths ---
    chroma_persist_dir: str = "./data/chroma"
    bm25_index_path: str = "./data/bm25_index.pkl"
    sqlite_db_path: str = "./data/metadata.db"

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()