"""Application configuration"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Service Info
    SERVICE_NAME: str = "acadlo-ai-core"
    SERVICE_VERSION: str = "0.2.0"
    
    # Server Config
    HTTP_PORT: int = 8000
    ENVIRONMENT: str = "development"
    
    # Database - PostgreSQL with asyncpg
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    DATABASE_URL: str = "postgresql+asyncpg://acadlo:acadlo_secret@localhost:5432/acadlo_ai"
    
    # Redis - for ARQ job queue
    REDIS_URL: str = "redis://redis:6379"
    
    # Embedding Provider (OpenAI)
    OPENAI_API_KEY: str = "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"  # Required for embedding generation
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small" 
    
    # LLM Provider Configuration
    LLM_PROVIDER: str = "openai"  # Provider type: "openai", "selfhosted", etc.
    LLM_API_KEY: str = ""  # Will use OPENAI_API_KEY if empty and provider is openai
    LLM_DEFAULT_CHAT_MODEL: str = "gpt-4o-mini"  # Default model for generic /v1/chat
    TUTOR_LLM_MODEL: str = "gpt-4o-mini"  # Dedicated tutor model for analysis + response generation
    LLM_TEMPERATURE: float = 0.7  # Default temperature for chat (0-2)
    LLM_MAX_TOKENS: int = 1000  # Default max completion tokens
    
    # Chunking Configuration
    CHUNK_SIZE: int = 500  # Target chunk size in characters (~125 tokens)
    CHUNK_OVERLAP: int = 50  # Overlap between chunks in characters
    
    # Chat RAG Configuration (US-AI-M3-B)
    CHAT_CONTEXT_TOP_K: int = 8  # Number of chunks to retrieve from search
    CHAT_CONTEXT_MAX_CHUNKS: int = 6  # Max chunks to include in LLM context
    CHAT_CONTEXT_MAX_CHARS: int = 6000  # Max total characters for context (~1500 tokens)
    CHAT_NO_KNOWLEDGE_MESSAGE: str = "I couldn't find any relevant information in the current knowledge base to answer your question."
    DEFAULT_LANGUAGE: str = "en"  # Fallback language when not provided
    
    # Chat History Configuration (US-AI-M3-D)
    CHAT_HISTORY_MAX_TURNS: int = 10  # Max conversation turns to include (5 Q&A pairs)
    CHAT_HISTORY_MAX_CHARS_PER_MESSAGE: int = 2000  # Max chars per history message
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080", "https://acadlo-ai.prefly.dev/"]

    # Uploads
    UPLOAD_DIR: str = "uploads"

    # Multimodal ingestion (PDF page vision enrichment)
    MULTIMODAL_INGESTION_ENABLED: bool = True
    MULTIMODAL_VISION_MODEL: str = "gpt-4o-mini"
    MULTIMODAL_MAX_PDF_PAGES: int = 120
    MULTIMODAL_PDF_RENDER_SCALE: float = 2.0
    MULTIMODAL_VISION_PAGES_PER_MINUTE: int = 20
    MULTIMODAL_VISION_RATE_LIMIT_RETRIES: int = 3
    MULTIMODAL_VISION_RETRY_BASE_SECONDS: float = 1.0

    # Worker runtime controls
    WORKER_MAX_JOBS: int = 2
    WORKER_JOB_TIMEOUT_SECONDS: int = 1800
    WORKER_MAX_TRIES: int = 3
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    def get_llm_api_key(self) -> str:
        """
        Get the appropriate API key for the configured LLM provider.
        
        Falls back to OPENAI_API_KEY if LLM_API_KEY is not set and provider is openai.
        """
        if self.LLM_API_KEY:
            return self.LLM_API_KEY
        if self.LLM_PROVIDER.lower() == "openai":
            return self.OPENAI_API_KEY
        return ""


# Global settings instance
settings = Settings()
