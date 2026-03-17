"""ARQ background tasks for document processing"""
import logging
from uuid import UUID
from typing import Dict, Any
from pathlib import Path
from urllib.parse import urlparse

from app.db.session import async_session_factory
from app.repositories import DocumentRepository, ChunkRepository, IngestionJobRepository
from app.services.extractor import ContentExtractor
from app.core.config import settings
from app.services.chunker import TextChunker
from app.providers.embedding import get_embedding_provider

# Use specific logger name to match logging_config.py handler
logger = logging.getLogger("ingestion_service")


async def process_ingestion_job(
    ctx: Dict[str, Any],
    job_id: str,
    document_id: str,
) -> Dict[str, Any]:
    """
    Background task to process a document ingestion job.
    
    This task:
    1. Loads the document from the database
    2. Extracts text content (handles text, PDF, URL)
    3. Chunks the content into smaller pieces
    4. Generates embeddings for all chunks (via OpenAI)
    5. Creates chunk records in the database with embeddings
    6. Updates job status (completed/failed)
    
    Args:
        ctx: ARQ context (contains redis connection)
        job_id: UUID string of the ingestion job
        document_id: UUID string of the document to process
        
    Returns:
        Dict with processing result summary
    """
    job_uuid = UUID(job_id)
    doc_uuid = UUID(document_id)
    
    logger.info(f"Starting ingestion job {job_id} for document {document_id}")
    
    async with async_session_factory() as session:
        job_repo = IngestionJobRepository(session)
        doc_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)
        
        try:
            # Mark job as processing
            await job_repo.mark_processing(job_uuid)
            await session.commit()
            
            # Load document
            document = await doc_repo.get_by_id(doc_uuid)
            if not document:
                raise ValueError(f"Document {document_id} not found")
            
            logger.info(f"Processing document: {document.title}")
            
            # Extract text content
            extractor = ContentExtractor()
            text_content = await extractor.extract(
                content_type=document.content_location_type,
                content_value=document.content_location_value,
                language=document.language,
            )
            
            if not text_content or not text_content.strip():
                raise ValueError("No text content extracted from document")
            
            logger.info(f"Extracted {len(text_content)} characters of text")

            # Delete uploaded file after successful extraction (if stored locally)
            _delete_local_upload_if_present(document.content_location_value)
            
            # Chunk the content
            chunker = TextChunker()
            chunks_data = chunker.chunk(
                text=text_content,
                document_id=doc_uuid,
                tenant_id=document.tenant_id,
                language=document.language,
                visibility_roles=document.visibility_roles,
                visibility_scopes=document.visibility_scopes,
                tags=document.tags,
            )
            
            logger.info(f"Created {len(chunks_data)} chunks")
            
            # Generate embeddings for all chunks
            if chunks_data:
                try:
                    logger.info("=" * 60)
                    logger.info("🔮 EMBEDDING GENERATION PHASE")
                    logger.info("=" * 60)
                    logger.info(f"📊 Number of chunks to embed: {len(chunks_data)}")
                    
                    # Get embedding provider
                    logger.info("🔧 Initializing embedding provider...")
                    embedding_provider = get_embedding_provider()
                    
                    # Extract chunk texts
                    chunk_texts = [chunk["text"] for chunk in chunks_data]
                    total_chars = sum(len(text) for text in chunk_texts)
                    logger.info(f"📝 Total characters to embed: {total_chars:,}")
                    
                    # Generate embeddings (batch call)
                    logger.info("🚀 Calling OpenAI API for batch embedding...")
                    embeddings = await embedding_provider.embed(chunk_texts)
                    
                    # Validate dimensions
                    expected_dim = embedding_provider.get_dimension()
                    actual_dim = len(embeddings[0]) if embeddings else 0
                    
                    logger.info(f"✅ Embedding API call successful!")
                    logger.info(f"   Expected dimension: {expected_dim}")
                    logger.info(f"   Actual dimension: {actual_dim}")
                    logger.info(f"   Embeddings received: {len(embeddings)}")
                    
                    if embeddings and actual_dim != expected_dim:
                        logger.error(f"❌ Dimension mismatch: got {actual_dim}, expected {expected_dim}")
                        raise ValueError(
                            f"Embedding dimension mismatch: got {actual_dim}, "
                            f"expected {expected_dim}"
                        )
                    
                    # Update chunks with embeddings
                    logger.info("💾 Attaching embeddings to chunks...")
                    for i, chunk in enumerate(chunks_data):
                        chunk["embedding"] = embeddings[i]
                        if i == 0:
                            # Log first embedding preview
                            preview = embeddings[i][:5]  # First 5 values
                            logger.info(f"   Sample embedding (first 5 values): {preview}")
                    
                    logger.info(f"✅ Successfully attached {len(embeddings)} embeddings to chunks")
                    logger.info("=" * 60)
                    
                    # Close the provider connection
                    await embedding_provider.close()
                    
                except Exception as e:
                    logger.error("=" * 60)
                    logger.error(f"❌ EMBEDDING GENERATION FAILED")
                    logger.error("=" * 60)
                    logger.error(f"Error type: {type(e).__name__}")
                    logger.error(f"Error message: {str(e)}")
                    logger.error("=" * 60)
                    raise Exception(f"Embedding generation failed: {str(e)}") from e
            
            # Create chunk records in database (with embeddings)
            if chunks_data:
                await chunk_repo.create_chunks_bulk(chunks_data)
            
            # Mark job as completed
            await job_repo.mark_completed(job_uuid, document_id=doc_uuid)
            await session.commit()
            
            logger.info(f"Ingestion job {job_id} completed successfully")
            
            return {
                "status": "completed",
                "job_id": job_id,
                "document_id": document_id,
                "chunks_created": len(chunks_data),
                "text_length": len(text_content),
                "embeddings_generated": len(chunks_data),
            }
            
        except Exception as e:
            logger.error(f"Ingestion job {job_id} failed: {str(e)}")
            
            # Mark job as failed
            await job_repo.mark_failed(job_uuid, error_message=str(e))
            await session.commit()
            
            return {
                "status": "failed",
                "job_id": job_id,
                "document_id": document_id,
                "error": str(e),
            }


def _delete_local_upload_if_present(content_url: str) -> None:
    """Delete locally stored upload if the URL points to /uploads."""
    try:
        parsed = urlparse(content_url)
        if not parsed.path.startswith("/uploads/"):
            return
        uploads_dir = Path(settings.UPLOAD_DIR).resolve()
        filename = parsed.path.replace("/uploads/", "", 1)
        file_path = (uploads_dir / filename).resolve()
        if not str(file_path).startswith(str(uploads_dir)):
            return
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted local upload file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to delete local upload file: {e}")
