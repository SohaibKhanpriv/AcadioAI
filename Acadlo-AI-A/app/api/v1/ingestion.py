"""Document ingestion endpoints"""
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Query, Depends, UploadFile, File, Form, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    DocumentIngestRequest,
    IngestionJobResponse,
    IngestionJobStatusResponse,
    ErrorResponse,
    Visibility,
    ContentPayload,
)
from app.services.ingestion_service import IngestionService
from app.db.session import get_session
from app.core.config import settings

router = APIRouter(prefix="/v1/ingest", tags=["Ingestion"])


@router.post(
    "/document",
    response_model=IngestionJobResponse,
    status_code=202,
    summary="Ingest a document",
    description="Submit a document for ingestion and processing. Returns a job ID for tracking the ingestion status.",
    responses={
        202: {
            "description": "Document accepted for ingestion",
            "content": {
                "application/json": {
                    "example": {
                        "jobId": "550e8400-e29b-41d4-a716-446655440000",
                        "status": "pending"
                    }
                }
            }
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid request payload",
            "content": {
                "application/json": {
                    "example": {
                        "errorCode": "VALIDATION_ERROR",
                        "message": "Invalid request payload",
                        "details": {
                            "fieldErrors": {
                                "tenantId": "Field is required"
                            }
                        },
                        "traceId": None
                    }
                }
            }
        }
    }
)
async def ingest_document(
    request: DocumentIngestRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Ingest a document for processing.
    
    The document will be:
    - Stored in the database
    - Queued for background processing via ARQ
    - Chunked into smaller pieces
    - (Future) Embedded for semantic search
    
    Returns a job ID that can be used to check processing status.
    """
    service = IngestionService(session)
    result = await service.ingest_document(request)
    return result


@router.post(
    "/upload",
    response_model=IngestionJobResponse,
    status_code=202,
    summary="Upload and ingest a document",
    description="Upload a file and ingest it by storing a local URL reference.",
    responses={
        202: {
            "description": "Document accepted for ingestion",
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid request payload",
        },
    },
)
async def ingest_upload(
    request: Request,
    file: UploadFile = File(...),
    tenantId: str = Form(...),
    title: str = Form(...),
    language: str = Form("en-US"),
    sourceType: str = Form("upload"),
    visibilityRoles: str = Form("user"),
    visibilityScopes: str = Form("public"),
    tags: str = Form("{}"),
    externalId: str | None = Form(None),
    metadata: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    service = IngestionService(session)

    # Parse tags/metadata JSON
    try:
        tags_dict = json.loads(tags) if tags else {}
        metadata_dict = json.loads(metadata) if metadata else None
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in tags or metadata")

    # Save uploaded file
    uploads_dir = Path(settings.UPLOAD_DIR)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower()
    if not ext:
        raise HTTPException(status_code=400, detail="File must have an extension")
    filename = f"{uuid4().hex}{ext}"
    file_path = uploads_dir / filename
    content = await file.read()
    file_path.write_bytes(content)

    # Build public URL
    base_url = str(request.base_url)
    if not base_url.endswith("/"):
        base_url += "/"
    file_url = f"{base_url}uploads/{filename}"

    visibility = Visibility(
        roles=[r.strip() for r in visibilityRoles.split(",") if r.strip()],
        scopes=[s.strip() for s in visibilityScopes.split(",") if s.strip()],
    )

    ingest_request = DocumentIngestRequest(
        tenantId=tenantId,
        externalId=externalId,
        title=title,
        language=language,
        sourceType=sourceType,
        visibility=visibility,
        tags=tags_dict,
        content=ContentPayload(type="url", value=file_url),
        metadata=metadata_dict,
    )

    result = await service.ingest_document(ingest_request)
    return result


@router.get(
    "/status",
    response_model=IngestionJobStatusResponse,
    summary="Get ingestion job status",
    description="Check the status of a document ingestion job by job ID",
    responses={
        200: {
            "description": "Job status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "jobId": "550e8400-e29b-41d4-a716-446655440000",
                        "tenantId": "t_abc",
                        "documentId": "660e8400-e29b-41d4-a716-446655440000",
                        "externalId": "Policy:42",
                        "status": "completed",
                        "errorMessage": None,
                        "createdAt": "2025-11-18T10:00:00Z",
                        "updatedAt": "2025-11-18T10:00:05Z"
                    }
                }
            }
        },
        404: {
            "model": ErrorResponse,
            "description": "Job not found",
            "content": {
                "application/json": {
                    "example": {
                        "errorCode": "NOT_FOUND",
                        "message": "Job with ID 'job_123' not found",
                        "details": {},
                        "traceId": None
                    }
                }
            }
        }
    }
)
async def get_job_status(
    jobId: str = Query(..., description="The job ID to check status for", example="550e8400-e29b-41d4-a716-446655440000"),
    session: AsyncSession = Depends(get_session),
):
    """
    Get the status of an ingestion job.
    
    Returns detailed information about the job including:
    - Current status (pending, processing, completed, failed)
    - Associated document ID (if created)
    - Error message (if failed)
    - Timestamps
    """
    service = IngestionService(session)
    result = await service.get_job_status(jobId)
    return result
