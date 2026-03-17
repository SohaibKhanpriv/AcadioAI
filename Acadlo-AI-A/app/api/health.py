"""Health and echo endpoints"""
from fastapi import APIRouter
from app.models.schemas import HealthResponse, EchoRequest, EchoResponse
from app.core.config import settings

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check if the service is running and healthy",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "service": "acadlo-ai-core",
                        "version": "0.1.0"
                    }
                }
            }
        }
    }
)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="ok",
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION
    )


@router.post(
    "/echo",
    response_model=EchoResponse,
    summary="Echo endpoint",
    description="Echo back any JSON payload sent in the request body",
    responses={
        200: {
            "description": "Successfully echoed the request payload",
            "content": {
                "application/json": {
                    "example": {
                        "echo": {
                            "message": "Hello, World!",
                            "timestamp": "2025-11-22T10:00:00Z"
                        }
                    }
                }
            }
        }
    }
)
async def echo(request: EchoRequest):
    """Echo endpoint - returns the same JSON payload"""
    return EchoResponse(echo=request.data)



