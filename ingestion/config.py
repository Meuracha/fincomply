"""
Shared configuration for FinComply ingestion pipeline.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Qdrant
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    collection_name: str = os.getenv("COLLECTION_NAME", "fincomply_docs")

    # Embedding
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Retrieval
    top_k_dense: int = 20       # dense vector search candidates
    top_k_rerank: int = 5       # after Cohere rerank
    bm25_weight: float = 0.3    # hybrid search weight (0=dense only, 1=BM25 only)

    # PostgreSQL
    postgres_host: str = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "fincomply_db")
    postgres_user: str = os.getenv("POSTGRES_USER", "fincomply")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "fincomply")

    # API Keys
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    cohere_api_key: str = os.getenv("COHERE_API_KEY", "")
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_base_url: str = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


config = Config()