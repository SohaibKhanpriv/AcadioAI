"""Exception handling middleware"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.exceptions import AcadloAIException, NotFoundError, ValidationError
import uuid


async def acadlo_exception_handler(request: Request, exc: AcadloAIException):
    """Handle custom Acadlo AI exceptions"""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    
    if isinstance(exc, NotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ValidationError):
        status_code = status.HTTP_400_BAD_REQUEST
    
    return JSONResponse(
        status_code=status_code,
        content={
            "errorCode": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "traceId": str(uuid.uuid4())
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    field_errors = {}
    for error in exc.errors():
        field = ".".join(str(x) for x in error["loc"][1:])  # Skip 'body'
        field_errors[field] = error["msg"]
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "errorCode": "VALIDATION_ERROR",
            "message": "Invalid request payload",
            "details": {"fieldErrors": field_errors},
            "traceId": str(uuid.uuid4())
        }
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "errorCode": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "details": {"error": str(exc)},
            "traceId": str(uuid.uuid4())
        }
    )

