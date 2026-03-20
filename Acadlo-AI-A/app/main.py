"""Main FastAPI application"""
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.exceptions import AcadloAIException
from app.middlewares.exception_middleware import (
    acadlo_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)
from app.api.health import router as health_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.search import router as search_router
from app.api.v1.chat import router as chat_router
from app.api.v1.llm_test import router as llm_test_router
from app.api.v1.tutor import router as tutor_router
from app.api.v1.topics import router as topics_router
from app.db.session import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    print(f"🚀 {settings.SERVICE_NAME} v{settings.SERVICE_VERSION} starting...")
    print(f"📝 API documentation available at http://localhost:{settings.HTTP_PORT}/docs")
    
    # Initialize logging system (US-AI-M3-E)
    setup_logging(
        log_dir="logs",
        retention_days=30,
        console_level="INFO",
        file_level="INFO"
    )
    
    # Initialize database connection
    try:
        await init_db()
        print("✅ Database connection established")
    except Exception as e:
        print(f"⚠️  Database connection failed: {e}")
        print("   Service will start but database operations will fail")
    
    yield
    
    # Shutdown
    print(f"👋 {settings.SERVICE_NAME} shutting down...")
    
    # Close database connections
    await close_db()
    print("✅ Database connections closed")


# Create FastAPI application
app = FastAPI(
    title="Acadlo AI Core",
    description="""Standalone AI service providing intelligent search and conversational AI capabilities using Retrieval-Augmented Generation (RAG).

## Features

* **Document Ingestion** - Upload and process documents for knowledge retrieval
* **Semantic Search** - Find relevant information across your document corpus
* **Conversational AI** - Ask questions and get contextual answers with citations
* **Multi-tenant** - Complete data isolation per tenant
* **Role-based Access** - Fine-grained visibility control
* **Multi-language** - Support for Arabic and English


""",
    version=settings.SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AcadloAIException, acadlo_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Ensure uploads directory exists and expose it
uploads_dir = Path(settings.UPLOAD_DIR)
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Include routers
app.include_router(health_router)
app.include_router(ingestion_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(llm_test_router, prefix="/v1/llm", tags=["LLM Testing"])
app.include_router(tutor_router)  # Tutor API (M4-G)
app.include_router(topics_router)  # Ingested Topics API


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.HTTP_PORT,
        reload=True
    )
