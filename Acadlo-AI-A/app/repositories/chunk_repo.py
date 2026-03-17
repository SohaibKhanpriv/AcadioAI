"""Repository for Chunk model operations"""
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import logging

from sqlalchemy import select, update, or_, func, text, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.db.models import Chunk, Document
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ChunkRepository(BaseRepository[Chunk]):
    """Repository for Chunk CRUD operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(Chunk, session)
    
    async def create_chunk(
        self,
        document_id: UUID,
        tenant_id: str,
        text: str,
        language: str,
        visibility_roles: List[str],
        visibility_scopes: List[str],
        tags: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        start_offset: Optional[int] = None,
        end_offset: Optional[int] = None,
    ) -> Chunk:
        """
        Create a new chunk.
        
        Args:
            document_id: Parent document UUID
            tenant_id: Tenant identifier
            text: Chunk text content
            language: Language code
            visibility_roles: List of roles that can access this chunk
            visibility_scopes: List of scopes for access control
            tags: Optional key-value metadata tags
            embedding: Optional vector embedding (1536 dimensions)
            start_offset: Optional start position in original document
            end_offset: Optional end position in original document
            
        Returns:
            Created Chunk instance
        """
        return await self.create(
            document_id=document_id,
            tenant_id=tenant_id,
            text=text,
            language=language,
            visibility_roles=visibility_roles,
            visibility_scopes=visibility_scopes,
            tags=tags or {},
            embedding=embedding,
            start_offset=start_offset,
            end_offset=end_offset,
        )
    
    async def create_chunks_bulk(
        self,
        chunks_data: List[Dict[str, Any]]
    ) -> List[Chunk]:
        """
        Create multiple chunks in bulk.
        
        Args:
            chunks_data: List of dictionaries with chunk field values
            
        Returns:
            List of created Chunk instances
        """
        chunks = [Chunk(**data) for data in chunks_data]
        self.session.add_all(chunks)
        await self.session.flush()
        for chunk in chunks:
            await self.session.refresh(chunk)
        return chunks
    
    async def get_by_document(
        self, 
        document_id: UUID,
        limit: int = 1000
    ) -> List[Chunk]:
        """
        Get all chunks for a document.
        
        Args:
            document_id: Document UUID
            limit: Maximum number of records
            
        Returns:
            List of chunks for the document
        """
        result = await self.session.execute(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .limit(limit)
            .order_by(Chunk.start_offset.asc().nullsfirst())
        )
        return list(result.scalars().all())
    
    async def get_by_tenant(
        self, 
        tenant_id: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Chunk]:
        """
        Get all chunks for a specific tenant.
        
        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of chunks for the tenant
        """
        result = await self.session.execute(
            select(Chunk)
            .where(Chunk.tenant_id == tenant_id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def update_embedding(
        self, 
        chunk_id: UUID, 
        embedding: List[float]
    ) -> Optional[Chunk]:
        """
        Update the embedding for a chunk.
        
        Args:
            chunk_id: Chunk UUID
            embedding: Vector embedding (1536 dimensions)
            
        Returns:
            Updated Chunk instance or None
        """
        return await self.update_by_id(chunk_id, embedding=embedding)
    
    async def update_embeddings_bulk(
        self,
        chunk_embeddings: List[Dict[str, Any]]
    ) -> int:
        """
        Update embeddings for multiple chunks.
        
        Args:
            chunk_embeddings: List of dicts with 'id' and 'embedding' keys
            
        Returns:
            Number of chunks updated
        """
        count = 0
        for item in chunk_embeddings:
            await self.session.execute(
                update(Chunk)
                .where(Chunk.id == item['id'])
                .values(embedding=item['embedding'])
            )
            count += 1
        await self.session.flush()
        return count
    
    async def vector_search(
        self,
        query_embedding: List[float],
        tenant_id: str,
        user_roles: List[str],
        top_k: int = 8,
        source_types: Optional[List[str]] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[Tuple[Chunk, Document, float]]:
        """
        Perform vector similarity search with filters.
        
        Uses pgvector's cosine distance operator (<=>) to find semantically similar chunks.
        
        Args:
            query_embedding: Query vector embedding (1536 dimensions)
            tenant_id: Tenant identifier for multi-tenant isolation
            user_roles: User's roles for visibility filtering
            top_k: Maximum number of results to return
            source_types: Optional list of source types to filter by
            subject: Optional subject to filter by (checks both chunk and document tags)
            grade: Optional grade to filter by (checks both chunk and document tags)
            tags: Optional tags dict to filter by (must match all key-value pairs)
            
        Returns:
            List of tuples: (Chunk, Document, similarity_score)
            Sorted by similarity score (highest first)
        """
        logger.info(f"🔍 Vector search: tenant={tenant_id}, roles={user_roles}, topK={top_k}")
        logger.debug(f"   Filters: source_types={source_types}, subject={subject}, grade={grade}, tags={tags}")
        
        # Build the base query with join
        query = (
            select(
                Chunk,
                Document,
                # Similarity score: 1 - cosine_distance (higher is better)
                (1 - Chunk.embedding.cosine_distance(query_embedding)).label('similarity_score')
            )
            .join(Document, Chunk.document_id == Document.id)
            .where(
                # Multi-tenant isolation (CRITICAL)
                Chunk.tenant_id == tenant_id,
                # Only chunks with embeddings
                Chunk.embedding.isnot(None),
            )
        )
        
        # Visibility filtering: empty roles OR roles intersect with user roles
        if user_roles:
            # User can see chunk if:
            # 1. visibility_roles is empty (public), OR
            # 2. visibility_roles overlaps with user's roles
            # Note: Cast user_roles to PostgreSQL text[] array for ?| operator
            query = query.where(
                or_(
                    func.jsonb_array_length(Chunk.visibility_roles) == 0,
                    Chunk.visibility_roles.op('?|')(
                        cast(user_roles, ARRAY(String))  # Cast to text[] array
                    )
                )
            )
        else:
            # No roles provided - only show public chunks (empty visibility_roles)
            query = query.where(
                func.jsonb_array_length(Chunk.visibility_roles) == 0
            )
        
        # Optional filter: source_type (from documents table)
        if source_types:
            query = query.where(Document.source_type.in_(source_types))
            logger.debug(f"   Applied source_type filter: {source_types}")
        
        # Optional filter: subject (check both chunk and document tags)
        if subject:
            query = query.where(
                or_(
                    Chunk.tags['subject'].astext == subject,
                    Document.tags['subject'].astext == subject
                )
            )
            logger.debug(f"   Applied subject filter: {subject}")
        
        # Optional filter: grade (check both chunk and document tags)
        if grade:
            query = query.where(
                or_(
                    Chunk.tags['grade'].astext == grade,
                    Document.tags['grade'].astext == grade
                )
            )
            logger.debug(f"   Applied grade filter: {grade}")
        
        # Optional filter: tags (must match ALL specified key-value pairs)
        # Uses case-insensitive comparison for tag values
        if tags:
            # Build conditions for each tag key-value pair (case-insensitive)
            tag_conditions = []
            for key, value in tags.items():
                # Check if chunk or document has this tag with matching value (case-insensitive)
                chunk_condition = func.lower(Chunk.tags[key].astext) == func.lower(value)
                doc_condition = func.lower(Document.tags[key].astext) == func.lower(value)
                # Match if either chunk or document has the tag
                tag_conditions.append(or_(chunk_condition, doc_condition))
            
            # All tag conditions must be true (AND logic)
            if tag_conditions:
                query = query.where(*tag_conditions)
                logger.debug(f"   Applied tags filter (case-insensitive): {tags}")
        
        # Order by similarity (ascending cosine distance = descending similarity)
        query = query.order_by(Chunk.embedding.cosine_distance(query_embedding))
        
        # Limit results
        query = query.limit(top_k)
        
        # Execute query
        result = await self.session.execute(query)
        rows = result.all()
        
        logger.info(f"✅ Found {len(rows)} results")
        if rows:
            logger.debug(f"   Top result similarity: {rows[0].similarity_score:.4f}")
        
        # Return as list of tuples: (Chunk, Document, similarity_score)
        return [(row.Chunk, row.Document, row.similarity_score) for row in rows]
    
    async def delete_by_document(self, document_id: UUID) -> int:
        """
        Delete all chunks for a document.
        
        Args:
            document_id: Document UUID
            
        Returns:
            Number of chunks deleted
        """
        from sqlalchemy import delete as sa_delete
        result = await self.session.execute(
            sa_delete(Chunk).where(Chunk.document_id == document_id)
        )
        await self.session.flush()
        return result.rowcount
