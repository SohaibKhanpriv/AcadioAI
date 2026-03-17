"""
Structured logging utilities for Acadlo AI Core.

This module provides helper functions for logging chat requests, ingestion jobs,
and errors with consistent structured format as per US-AI-M3-E requirements.
"""

from typing import Optional, Dict, Any
from datetime import datetime
import logging
import traceback
import uuid

from app.core.logging_config import get_structured_logger


# Module loggers
chat_logger = get_structured_logger("chat_service")
ingestion_logger = get_structured_logger("ingestion_service")
error_logger = get_structured_logger("error")


def log_chat_request(
    tenant_id: str,
    user_id: Optional[str],
    scenario: Optional[str],
    endpoint: str = "/v1/chat",
    history_turns: int = 0,
    language: Optional[str] = None,
    language_defaulted: bool = False,
    retrieved_chunks: int = 0,
    used_chunks: int = 0,
    model: Optional[str] = None,
    llm_latency_ms: Optional[float] = None,
    total_latency_ms: float = 0.0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    no_knowledge: bool = False,
    http_status: int = 200,
    trace_id: Optional[str] = None,
    additional_metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log a structured chat request with all required metadata.
    
    This function logs metadata only, avoiding full messages, responses, or chunk content.
    
    Args:
        tenant_id: Tenant identifier
        user_id: User identifier (optional)
        scenario: Usage scenario (optional)
        endpoint: API endpoint (default: /v1/chat)
        history_turns: Number of conversation turns in request history
        language: Language code (e.g., "en", "es")
        language_defaulted: Whether language was auto-detected or defaulted
        retrieved_chunks: Number of chunks returned by vector search
        used_chunks: Number of chunks included in LLM context
        model: LLM model used (e.g., "gpt-4o-mini")
        llm_latency_ms: Time taken by LLM provider call
        total_latency_ms: Total request processing time
        prompt_tokens: Tokens in prompt
        completion_tokens: Tokens in completion
        total_tokens: Total tokens used
        no_knowledge: Whether "no knowledge" fallback was triggered
        http_status: HTTP response status code
        trace_id: Unique request trace identifier
        additional_metadata: Any extra fields to log
    """
    log_data = {
        "endpoint": endpoint,
        "tenantId": tenant_id,
        "userId": user_id,
        "scenario": scenario,
        "historyTurns": history_turns,
        "language": language,
        "languageDefaulted": language_defaulted,
        "retrievedChunks": retrieved_chunks,
        "usedChunks": used_chunks,
        "model": model,
        "llmLatencyMs": round(llm_latency_ms, 2) if llm_latency_ms else None,
        "totalLatencyMs": round(total_latency_ms, 2),
        "promptTokens": prompt_tokens,
        "completionTokens": completion_tokens,
        "totalTokens": total_tokens,
        "noKnowledge": no_knowledge,
        "httpStatus": http_status,
        "traceId": trace_id or generate_trace_id(),
    }
    
    # Remove None values for cleaner logs
    log_data = {k: v for k, v in log_data.items() if v is not None}
    
    # Merge additional metadata if provided
    if additional_metadata:
        log_data.update(additional_metadata)
    
    # Log at INFO level for successful requests, WARN for 4xx, ERROR for 5xx
    log_level = logging.INFO
    log_message = "Chat request processed"
    
    if http_status >= 500:
        log_level = logging.ERROR
        log_message = "Chat request failed (server error)"
    elif http_status >= 400:
        log_level = logging.WARNING
        log_message = "Chat request failed (client error)"
    
    chat_logger.log(log_level, log_message, extra_fields=log_data)


def log_chat_error(
    error_type: str,
    error_message: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    scenario: Optional[str] = None,
    trace_id: Optional[str] = None,
    exception: Optional[Exception] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log a chat error with structured details.
    
    Args:
        error_type: Type of error (e.g., "validation", "search_failure", "llm_failure", "unexpected")
        error_message: Human-readable error description
        tenant_id: Tenant identifier
        user_id: User identifier (optional)
        scenario: Usage scenario (optional)
        trace_id: Request trace identifier
        exception: The exception object (if available)
        additional_context: Extra context fields
    """
    log_data = {
        "errorType": error_type,
        "errorMessage": error_message,
        "tenantId": tenant_id,
        "userId": user_id,
        "scenario": scenario,
        "traceId": trace_id or generate_trace_id(),
    }
    
    # Add exception details if present
    if exception:
        log_data["exceptionType"] = type(exception).__name__
        log_data["exceptionDetails"] = str(exception)
        log_data["stackTrace"] = traceback.format_exc()
    
    # Merge additional context
    if additional_context:
        log_data.update(additional_context)
    
    # Remove None values
    log_data = {k: v for k, v in log_data.items() if v is not None}
    
    error_logger.error(f"Chat error: {error_type}", extra_fields=log_data)


def log_ingestion_job(
    job_id: str,
    tenant_id: str,
    document_id: str,
    status: str,
    source_type: str,
    chunks_created: int = 0,
    processing_time_ms: Optional[float] = None,
    error_message: Optional[str] = None,
    additional_metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log an ingestion job completion or failure.
    
    Args:
        job_id: Unique job identifier
        tenant_id: Tenant identifier
        document_id: Document being processed
        status: Job status (e.g., "completed", "failed")
        source_type: Document source type (e.g., "text", "pdf", "url")
        chunks_created: Number of chunks created
        processing_time_ms: Total processing time
        error_message: Error message if failed
        additional_metadata: Extra fields to log
    """
    log_data = {
        "jobId": job_id,
        "tenantId": tenant_id,
        "documentId": document_id,
        "status": status,
        "sourceType": source_type,
        "chunksCreated": chunks_created,
        "processingTimeMs": round(processing_time_ms, 2) if processing_time_ms else None,
        "errorMessage": error_message,
    }
    
    # Remove None values
    log_data = {k: v for k, v in log_data.items() if v is not None}
    
    # Merge additional metadata
    if additional_metadata:
        log_data.update(additional_metadata)
    
    # Log at appropriate level
    log_level = logging.INFO if status == "completed" else logging.ERROR
    log_message = f"Ingestion job {status}: {document_id}"
    
    ingestion_logger.log(log_level, log_message, extra_fields=log_data)


def log_ingestion_error(
    error_type: str,
    error_message: str,
    tenant_id: str,
    document_id: Optional[str] = None,
    job_id: Optional[str] = None,
    exception: Optional[Exception] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log an ingestion error with structured details.
    
    Args:
        error_type: Type of error (e.g., "extraction_failed", "chunking_failed", "embedding_failed")
        error_message: Human-readable error description
        tenant_id: Tenant identifier
        document_id: Document identifier (if available)
        job_id: Job identifier (if available)
        exception: The exception object (if available)
        additional_context: Extra context fields
    """
    log_data = {
        "errorType": error_type,
        "errorMessage": error_message,
        "tenantId": tenant_id,
        "documentId": document_id,
        "jobId": job_id,
    }
    
    # Add exception details if present
    if exception:
        log_data["exceptionType"] = type(exception).__name__
        log_data["exceptionDetails"] = str(exception)
        log_data["stackTrace"] = traceback.format_exc()
    
    # Merge additional context
    if additional_context:
        log_data.update(additional_context)
    
    # Remove None values
    log_data = {k: v for k, v in log_data.items() if v is not None}
    
    error_logger.error(f"Ingestion error: {error_type}", extra_fields=log_data)


def generate_trace_id() -> str:
    """
    Generate a unique trace identifier for request tracking.
    
    Returns:
        UUID4 string (e.g., "a5d4095e-c720-4291-8e16-e4ccc7d468e8")
    """
    return str(uuid.uuid4())


def truncate_string(value: str, max_length: int = 100) -> str:
    """
    Safely truncate a string for logging purposes.
    
    Args:
        value: String to truncate
        max_length: Maximum allowed length
    
    Returns:
        Truncated string with "..." suffix if truncated
    """
    if len(value) <= max_length:
        return value
    return value[:max_length - 3] + "..."


