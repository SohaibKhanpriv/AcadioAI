"""Repository for Document model operations"""
from typing import Optional, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """Repository for Document CRUD operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(Document, session)
    
    async def create_document(
        self,
        tenant_id: str,
        title: str,
        language: str,
        source_type: str,
        visibility_roles: List[str],
        visibility_scopes: List[str],
        content_location_type: str,
        content_location_value: str,
        external_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Document:
        """
        Create a new document.
        
        Args:
            tenant_id: Tenant identifier
            title: Document title
            language: Language code (e.g., "ar-JO", "en-US")
            source_type: Source type (e.g., "policy", "curriculum")
            visibility_roles: List of roles that can access this document
            visibility_scopes: List of scopes for access control
            content_location_type: "text" or "blob"
            content_location_value: Full text content or URL/path
            external_id: Optional external system reference
            tags: Optional key-value metadata tags
            metadata: Optional additional metadata
            
        Returns:
            Created Document instance
        """
        return await self.create(
            tenant_id=tenant_id,
            external_id=external_id,
            title=title,
            language=language,
            source_type=source_type,
            visibility_roles=visibility_roles,
            visibility_scopes=visibility_scopes,
            tags=tags or {},
            content_location_type=content_location_type,
            content_location_value=content_location_value,
            doc_metadata=metadata or {},
        )
    
    async def get_by_tenant(
        self, 
        tenant_id: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Document]:
        """
        Get all documents for a specific tenant.
        
        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of documents for the tenant
        """
        result = await self.session.execute(
            select(Document)
            .where(Document.tenant_id == tenant_id)
            .limit(limit)
            .offset(offset)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_by_external_id(
        self, 
        tenant_id: str, 
        external_id: str
    ) -> Optional[Document]:
        """
        Get a document by its external ID within a tenant.
        
        Args:
            tenant_id: Tenant identifier
            external_id: External system reference
            
        Returns:
            Document instance or None
        """
        result = await self.session.execute(
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.external_id == external_id
            )
        )
        return result.scalar_one_or_none()
    
    async def get_by_source_type(
        self, 
        tenant_id: str, 
        source_type: str,
        limit: int = 100
    ) -> List[Document]:
        """
        Get documents by source type within a tenant.
        
        Args:
            tenant_id: Tenant identifier
            source_type: Source type to filter by
            limit: Maximum number of records
            
        Returns:
            List of matching documents
        """
        result = await self.session.execute(
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.source_type == source_type
            )
            .limit(limit)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())
