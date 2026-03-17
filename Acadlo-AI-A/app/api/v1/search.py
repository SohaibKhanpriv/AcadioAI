"""Search endpoint"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import SearchRequest, SearchResponse, ErrorResponse
from app.services.search_service import SearchService
from app.db.session import get_session
from app.repositories.chunk_repo import ChunkRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["Search"])


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Semantic search",
    description="Perform semantic vector search across ingested documents. Returns relevant chunks ranked by similarity score using pgvector.",
    responses={
        200: {
            "description": "Search completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "results": [
                            {
                                "chunkId": "chunk_987",
                                "documentId": "doc_123",
                                "text": "The policy for student transfers requires approval from both the sending and receiving school principals...",
                                "score": 0.89,
                                "title": "Transfer Policy",
                                "tags": {
                                    "stage": "Primary"
                                }
                            }
                        ]
                    }
                }
            }
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid request payload (e.g., missing tenantId)"
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error (e.g., embedding generation failed)"
        }
    }
)
async def search(
    request: SearchRequest,
    db_session: AsyncSession = Depends(get_session)
):
    """
    Perform semantic vector search across documents.
    
    **How it works:**
    1. Validates tenantId is present (required for multi-tenant isolation)
    2. Generates embedding for the query using OpenAI
    3. Performs vector similarity search using pgvector (cosine distance)
    4. Applies tenant isolation (only searches tenant's data)
    5. Applies role-based visibility filtering
    6. Applies optional filters (sourceType, subject, grade)
    7. Returns top-K most similar chunks with similarity scores
    
    **Multi-tenant Safety:**
    - Tenant T1 can NEVER see Tenant T2's data
    - All queries are restricted by tenantId
    
    **Visibility Filtering:**
    - Users only see chunks where:
      - visibility_roles is empty (public), OR
      - visibility_roles overlaps with user's roles
    
    **Filters:**
    - `sourceType`: Filters by document source type (e.g., "policy", "guide")
    - `subject`: Filters by subject tag (checks both chunk and document tags)
    - `grade`: Filters by grade tag (checks both chunk and document tags)
    
    **Note:** 
    - Empty query returns empty results (not an error)
    - visibility_scopes filtering is not yet implemented (reserved for future)
    """
    # Validate tenantId
    if not request.tenantId or not request.tenantId.strip():
        logger.warning("❌ Search request missing tenantId")
        raise HTTPException(
            status_code=400,
            detail="tenantId is required for search"
        )
    
    try:
        # Initialize service with dependencies
        chunk_repo = ChunkRepository(db_session)
        search_service = SearchService(db_session, chunk_repo)
        
        # Perform search
        result = await search_service.search(request)
        
        return result
        
    except ValueError as e:
        # Validation errors (e.g., missing tenantId)
        logger.error(f"❌ Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
        
    except Exception as e:
        # Internal errors (e.g., embedding generation failed, DB error)
        logger.error(f"❌ Search failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )



