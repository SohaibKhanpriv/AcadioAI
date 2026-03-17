"""Ingestion service for document processing with database and ARQ"""
import logging
from typing import Optional
from uuid import UUID

from arq import create_pool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.db.session import async_session_factory
from app.repositories import DocumentRepository, IngestionJobRepository
from app.models.schemas import (
    DocumentIngestRequest,
    IngestionJobResponse,
    IngestionJobStatusResponse,
)
from app.workers.settings import redis_settings

# Use specific logger name to match logging_config.py handler
logger = logging.getLogger("ingestion_service")


class IngestionService:
    """
    Service for handling document ingestion.
    
    Creates documents and jobs in the database, then enqueues
    background tasks for processing via ARQ.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the service with a database session.
        
        Args:
            session: Async SQLAlchemy session
        """
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.job_repo = IngestionJobRepository(session)
    
    async def ingest_document(
        self, 
        request: DocumentIngestRequest
    ) -> IngestionJobResponse:
        """
        Create a document and enqueue it for background processing.
        
        This method:
        1. Creates a Document record in the database
        2. Creates an IngestionJob record (status=pending)
        3. Enqueues an ARQ task for background processing
        4. Returns the job ID for status tracking
        
        Args:
            request: Document ingestion request with all metadata
            
        Returns:
            IngestionJobResponse with jobId and initial status
        """
        logger.info(f"Starting document ingestion for tenant {request.tenantId}")
        
        # Create the document record
        document = await self.doc_repo.create_document(
            tenant_id=request.tenantId,
            external_id=request.externalId,
            title=request.title,
            language=request.language,
            source_type=request.sourceType,
            visibility_roles=request.visibility.roles,
            visibility_scopes=request.visibility.scopes,
            tags=request.tags,
            content_location_type=request.content.type,
            content_location_value=request.content.value,
            metadata=request.metadata,
        )
        
        logger.info(f"Created document {document.id} for tenant {request.tenantId}")
        
        # Create the ingestion job
        job = await self.job_repo.create_job(
            tenant_id=request.tenantId,
            document_id=document.id,
            status="pending",
        )
        
        logger.info(f"Created ingestion job {job.id}")
        
        # Commit the transaction to ensure records are persisted
        await self.session.commit()
        
        # Enqueue the background task
        try:
            redis_pool = await create_pool(redis_settings)
            await redis_pool.enqueue_job(
                "process_ingestion_job",
                str(job.id),
                str(document.id),
            )
            await redis_pool.close()
            logger.info(f"Enqueued background task for job {job.id}")
        except Exception as e:
            logger.error(f"Failed to enqueue job {job.id}: {e}")
            # Mark job as failed if we can't enqueue
            await self.job_repo.mark_failed(job.id, f"Failed to enqueue: {str(e)}")
            await self.session.commit()
        
        return IngestionJobResponse(
            jobId=str(job.id),
            status=job.status,
        )
    
    async def get_job_status(self, job_id: str) -> IngestionJobStatusResponse:
        """
        Get the status of an ingestion job.
        
        Args:
            job_id: UUID string of the job
            
        Returns:
            IngestionJobStatusResponse with current job status
            
        Raises:
            NotFoundError: If job doesn't exist
        """
        try:
            job_uuid = UUID(job_id)
        except ValueError:
            raise NotFoundError(f"Invalid job ID format: '{job_id}'")
        
        job = await self.job_repo.get_by_id(job_uuid)
        
        if not job:
            raise NotFoundError(f"Job with ID '{job_id}' not found")
        
        # Get associated document to retrieve external_id
        external_id = None
        if job.document_id:
            document = await self.doc_repo.get_by_id(job.document_id)
            if document:
                external_id = document.external_id
        
        return IngestionJobStatusResponse(
            jobId=str(job.id),
            tenantId=job.tenant_id,
            documentId=str(job.document_id) if job.document_id else None,
            externalId=external_id,
            status=job.status,
            errorMessage=job.error_message,
            createdAt=job.created_at,
            updatedAt=job.updated_at,
        )
