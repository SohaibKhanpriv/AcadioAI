"""Repository for IngestionJob model operations"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IngestionJob
from app.repositories.base import BaseRepository


class IngestionJobRepository(BaseRepository[IngestionJob]):
    """Repository for IngestionJob CRUD operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(IngestionJob, session)
    
    async def create_job(
        self,
        tenant_id: str,
        document_id: Optional[UUID] = None,
        status: str = "pending",
    ) -> IngestionJob:
        """
        Create a new ingestion job.
        
        Args:
            tenant_id: Tenant identifier
            document_id: Optional associated document UUID
            status: Initial status (default: "pending")
            
        Returns:
            Created IngestionJob instance
        """
        return await self.create(
            tenant_id=tenant_id,
            document_id=document_id,
            status=status,
        )
    
    async def get_by_tenant(
        self, 
        tenant_id: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[IngestionJob]:
        """
        Get all jobs for a specific tenant.
        
        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of jobs for the tenant
        """
        result = await self.session.execute(
            select(IngestionJob)
            .where(IngestionJob.tenant_id == tenant_id)
            .limit(limit)
            .offset(offset)
            .order_by(IngestionJob.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_pending_jobs(self, limit: int = 10) -> List[IngestionJob]:
        """
        Get pending jobs for processing.
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of pending jobs
        """
        result = await self.session.execute(
            select(IngestionJob)
            .where(IngestionJob.status == "pending")
            .limit(limit)
            .order_by(IngestionJob.created_at.asc())
        )
        return list(result.scalars().all())
    
    async def get_by_status(
        self, 
        status: str, 
        tenant_id: Optional[str] = None,
        limit: int = 100
    ) -> List[IngestionJob]:
        """
        Get jobs by status, optionally filtered by tenant.
        
        Args:
            status: Job status to filter by
            tenant_id: Optional tenant filter
            limit: Maximum number of records
            
        Returns:
            List of matching jobs
        """
        query = select(IngestionJob).where(IngestionJob.status == status)
        
        if tenant_id:
            query = query.where(IngestionJob.tenant_id == tenant_id)
        
        result = await self.session.execute(
            query.limit(limit).order_by(IngestionJob.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def update_status(
        self,
        job_id: UUID,
        status: str,
        error_message: Optional[str] = None,
        document_id: Optional[UUID] = None,
    ) -> Optional[IngestionJob]:
        """
        Update job status with appropriate timestamps.
        
        Args:
            job_id: Job UUID
            status: New status
            error_message: Optional error message (for failed status)
            document_id: Optional document ID to associate
            
        Returns:
            Updated IngestionJob instance or None
        """
        update_values = {"status": status}
        
        if document_id is not None:
            update_values["document_id"] = document_id
        
        if error_message is not None:
            update_values["error_message"] = error_message
        
        # Set appropriate timestamps based on status
        now = datetime.utcnow()
        if status == "processing":
            update_values["started_at"] = now
        elif status in ("completed", "failed"):
            update_values["finished_at"] = now
        
        await self.session.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job_id)
            .values(**update_values)
        )
        await self.session.flush()
        return await self.get_by_id(job_id)
    
    async def mark_processing(self, job_id: UUID) -> Optional[IngestionJob]:
        """
        Mark a job as processing.
        
        Args:
            job_id: Job UUID
            
        Returns:
            Updated IngestionJob instance or None
        """
        return await self.update_status(job_id, "processing")
    
    async def mark_completed(
        self, 
        job_id: UUID,
        document_id: Optional[UUID] = None
    ) -> Optional[IngestionJob]:
        """
        Mark a job as completed.
        
        Args:
            job_id: Job UUID
            document_id: Optional document ID to associate
            
        Returns:
            Updated IngestionJob instance or None
        """
        return await self.update_status(job_id, "completed", document_id=document_id)
    
    async def mark_failed(
        self, 
        job_id: UUID, 
        error_message: str
    ) -> Optional[IngestionJob]:
        """
        Mark a job as failed.
        
        Args:
            job_id: Job UUID
            error_message: Error description
            
        Returns:
            Updated IngestionJob instance or None
        """
        return await self.update_status(job_id, "failed", error_message=error_message)
