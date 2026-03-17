"""Search service for semantic search"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.models.schemas import SearchRequest, SearchResponse, SearchResultItem
from app.repositories.chunk_repo import ChunkRepository
from app.providers.embedding import EmbeddingProvider, get_embedding_provider
from app.db.session import get_session

logger = logging.getLogger(__name__)


class SearchService:
    """Service for handling semantic search with vector similarity"""
    
    def __init__(
        self,
        db_session: AsyncSession,
        chunk_repo: ChunkRepository,
    ):
        self.db_session = db_session
        self.chunk_repo = chunk_repo
        self.embedding_provider: Optional[EmbeddingProvider] = None
    
    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Perform semantic vector search across ingested documents.
        
        Process:
        1. Validate tenantId is present
        2. Generate embedding for the query text
        3. Perform vector similarity search with filters
        4. Return ranked results
        
        Args:
            request: Search request with query, filters, and access control
            
        Returns:
            SearchResponse with ranked results
            
        Raises:
            ValueError: If tenantId is missing
            Exception: If embedding generation or search fails
        """
        logger.info("=" * 60)
        logger.info("🔎 SEARCH REQUEST")
        logger.info("=" * 60)
        logger.info(f"👤 Tenant: {request.tenantId}")
        logger.info(f"👤 User: {request.userId}")
        logger.info(f"🎭 Roles: {request.roles}")
        logger.info(f"🔤 Language: {request.language}")
        logger.info(f"❓ Query: {request.query[:100]}...")
        logger.info(f"📊 Top K: {request.topK}")
        
        # 1. Validate tenantId
        if not request.tenantId or not request.tenantId.strip():
            logger.error("❌ tenantId is required but was not provided")
            raise ValueError("tenantId is required")
        
        # 2. Handle empty query gracefully
        if not request.query or not request.query.strip():
            logger.info("⚠️  Empty query provided, returning empty results")
            return SearchResponse(results=[])
        
        # 3. Generate query embedding
        try:
            logger.info("🔮 Generating query embedding...")
            self.embedding_provider = get_embedding_provider()
            query_embeddings = await self.embedding_provider.embed([request.query])
            query_embedding = query_embeddings[0]
            logger.info(f"✅ Query embedding generated (dimension: {len(query_embedding)})")
        except Exception as e:
            logger.error(f"❌ Failed to generate query embedding: {str(e)}")
            raise Exception(f"Failed to generate query embedding: {str(e)}") from e
        
        # 4. Extract filters
        source_types = request.filters.sourceType if request.filters else None
        subject = request.filters.subject if request.filters else None
        grade = request.filters.grade if request.filters else None
        tags = request.filters.tags if request.filters else None
        
        if request.filters:
            logger.info(f"🔍 Filters applied:")
            if source_types:
                logger.info(f"   - Source types: {source_types}")
            if subject:
                logger.info(f"   - Subject: {subject}")
            if grade:
                logger.info(f"   - Grade: {grade}")
            if tags:
                logger.info(f"   - Tags: {tags}")
        
        # 5. Perform vector search
        try:
            logger.info("🚀 Executing vector similarity search...")
            search_results = await self.chunk_repo.vector_search(
                query_embedding=query_embedding,
                tenant_id=request.tenantId,
                user_roles=request.roles,
                top_k=request.topK,
                source_types=source_types,
                subject=subject,
                grade=grade,
                tags=tags,
            )
            
            logger.info(f"✅ Search completed: {len(search_results)} results found")
            
        except Exception as e:
            logger.error(f"❌ Vector search failed: {str(e)}")
            raise Exception(f"Vector search failed: {str(e)}") from e
        
        # 6. Map to response format
        result_items = []
        for i, (chunk, document, similarity_score) in enumerate(search_results):
            # Merge tags: prefer chunk tags, fallback to document tags
            merged_tags = {**(document.tags or {}), **(chunk.tags or {})}
            
            result_item = SearchResultItem(
                chunkId=str(chunk.id),
                documentId=str(document.id),
                text=chunk.text,
                score=float(similarity_score),  # Ensure it's a float
                title=document.title,
                tags=merged_tags
            )
            result_items.append(result_item)
            
            if i == 0:
                logger.info(f"📌 Top result: '{document.title}' (score: {similarity_score:.4f})")
        
        logger.info("=" * 60)
        
        # 7. Close embedding provider
        if self.embedding_provider:
            await self.embedding_provider.close()
        
        return SearchResponse(results=result_items)



