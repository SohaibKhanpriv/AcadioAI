"""
Ingested Topics API.

Exposes endpoints for listing topics extracted during document ingestion.

Endpoints:
- GET /v1/topics?tenant_id=...&subject=... — list topics for a tenant
- GET /v1/topics/{topic_id}              — get a single topic by ID
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.schemas import IngestedTopicItem, IngestedTopicListResponse
from app.repositories.ingested_topic_repo import IngestedTopicRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/topics", tags=["Topics"])


def _topic_to_item(topic) -> IngestedTopicItem:
    return IngestedTopicItem(
        id=str(topic.id),
        topic_name=topic.topic_name,
        subject=topic.subject,
        description=topic.description or "",
        grade_level=topic.grade_level,
        suggested_objectives=topic.suggested_objectives or [],
        document_id=str(topic.document_id),
        created_at=topic.created_at,
    )


@router.get(
    "",
    response_model=IngestedTopicListResponse,
    summary="List ingested topics for a tenant",
)
async def list_topics(
    tenant_id: str = Query(..., min_length=1, description="Tenant identifier"),
    subject: str | None = Query(None, description="Optional subject filter"),
    limit: int = Query(100, ge=1, le=500, description="Max topics to return"),
    db: AsyncSession = Depends(get_session),
) -> IngestedTopicListResponse:
    repo = IngestedTopicRepository(db)

    if subject:
        topics = await repo.find_by_tenant_and_subject(tenant_id, subject, limit=limit)
    else:
        topics = await repo.find_by_tenant(tenant_id, limit=limit)

    items = [_topic_to_item(t) for t in topics]
    return IngestedTopicListResponse(
        tenant_id=tenant_id,
        topics=items,
        total=len(items),
    )


@router.get(
    "/{topic_id}",
    response_model=IngestedTopicItem,
    summary="Get a single ingested topic by ID",
)
async def get_topic(
    topic_id: str,
    db: AsyncSession = Depends(get_session),
) -> IngestedTopicItem:
    repo = IngestedTopicRepository(db)
    try:
        topic = await repo.get_by_id(UUID(topic_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid topic ID format")

    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    return _topic_to_item(topic)
