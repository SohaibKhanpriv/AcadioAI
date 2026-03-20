"""Repository for IngestedTopic model operations"""
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import logging

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IngestedTopic, Document
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class IngestedTopicRepository(BaseRepository[IngestedTopic]):
    """Repository for IngestedTopic CRUD and vector search operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(IngestedTopic, session)

    async def create_topics_bulk(
        self,
        topics_data: List[Dict[str, Any]],
    ) -> List[IngestedTopic]:
        """Batch-insert multiple IngestedTopic records."""
        topics = [IngestedTopic(**data) for data in topics_data]
        self.session.add_all(topics)
        await self.session.flush()
        for t in topics:
            await self.session.refresh(t)
        return topics

    async def find_by_tenant_and_subject(
        self,
        tenant_id: str,
        subject: str,
        limit: int = 50,
    ) -> List[IngestedTopic]:
        """Return all topics for a tenant filtered by subject."""
        result = await self.session.execute(
            select(IngestedTopic)
            .where(
                IngestedTopic.tenant_id == tenant_id,
                IngestedTopic.subject == subject,
            )
            .order_by(IngestedTopic.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_by_tenant(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> List[IngestedTopic]:
        """Return all topics for a tenant."""
        result = await self.session.execute(
            select(IngestedTopic)
            .where(IngestedTopic.tenant_id == tenant_id)
            .order_by(IngestedTopic.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_by_document(
        self,
        document_id: UUID,
    ) -> List[IngestedTopic]:
        """Return all topics extracted from a specific document."""
        result = await self.session.execute(
            select(IngestedTopic)
            .where(IngestedTopic.document_id == document_id)
            .order_by(IngestedTopic.created_at.asc())
        )
        return list(result.scalars().all())

    async def vector_search_topics(
        self,
        query_embedding: List[float],
        tenant_id: str,
        subject: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Tuple[IngestedTopic, float]]:
        """
        Semantic similarity search over ingested topics.

        Returns list of (IngestedTopic, similarity_score) sorted by score desc.
        """
        query = (
            select(
                IngestedTopic,
                (1 - IngestedTopic.topic_embedding.cosine_distance(query_embedding))
                .label("similarity_score"),
            )
            .where(
                IngestedTopic.tenant_id == tenant_id,
                IngestedTopic.topic_embedding.isnot(None),
            )
        )

        if subject:
            query = query.where(IngestedTopic.subject == subject)

        query = (
            query.order_by(
                IngestedTopic.topic_embedding.cosine_distance(query_embedding)
            )
            .limit(top_k)
        )

        result = await self.session.execute(query)
        rows = result.all()
        return [(row.IngestedTopic, row.similarity_score) for row in rows]
