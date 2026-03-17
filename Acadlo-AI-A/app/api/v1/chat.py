"""Chat/conversational RAG endpoint"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ChatRequest, ChatResponse, ErrorResponse
from app.services.chat_service import ChatService, LLMProviderError, ChatValidationError
from app.db.session import get_session
from app.utils.logger import log_chat_error, generate_trace_id
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["Chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Conversational AI chat with RAG",
    description="Send a message to the AI assistant and receive a contextual response based on ingested documents using Retrieval-Augmented Generation.",
    responses={
        200: {
            "description": "Chat response generated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "sessionId": "sess_123",
                        "answer": "To transfer a student from one class to another, you must follow these steps: 1) Obtain approval from the current school principal...",
                        "language": "en",
                        "citations": [
                            {
                                "documentId": "doc_123",
                                "chunkId": "chunk_987",
                                "title": "Student Transfer Policy"
                            }
                        ],
                        "meta": {
                            "model": "gpt-4o-mini",
                            "retrievedChunks": 8,
                            "usedChunks": 4,
                            "promptTokens": 850,
                            "completionTokens": 120,
                            "totalTokens": 970,
                            "latencyMs": 2300
                        }
                    }
                }
            }
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid request payload (validation error)"
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error"
        },
        502: {
            "model": ErrorResponse,
            "description": "Bad Gateway - LLM provider failure"
        }
    }
)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_session)
):
    """
    Conversational AI chat with RAG (Retrieval-Augmented Generation).
    
    **RAG Pipeline (Milestone 3-B):**
    1. **Validation**: Validates tenantId and message are present
    2. **Retrieval**: Searches for relevant chunks using vector similarity
    3. **Context Selection**: Selects top chunks within token/char limits
    4. **Prompt Construction**: Builds system prompt + history + context + question
    5. **LLM Generation**: Calls configured LLM provider for answer
    6. **Response**: Returns answer with citations and metadata
    
    **Features:**
    - Full RAG with semantic search and LLM generation
    - Tenant isolation and role-based access control
    - Multi-turn conversation support via history (M3-D)
    - Cross-language support (multilingual embeddings)
    - Citations for all factual claims
    - "No knowledge" handling when no relevant context found
    - Configurable context limits and model parameters
    
    **Multi-Turn Conversations (M3-D):**
    - Provide `history` array with previous turns (user/assistant messages)
    - History is automatically limited to last CHAT_HISTORY_MAX_TURNS (default: 10)
    - Individual messages truncated to CHAT_HISTORY_MAX_CHARS_PER_MESSAGE (default: 2000)
    - Client is responsible for managing and sending history (stateless API)
    - Maintain same `sessionId` across turns for tracking
    
    **No Knowledge Behavior:**
    - If search returns zero chunks, returns a standard message without LLM call
    - Prevents hallucinations on topics outside the knowledge base
    
    **Error Handling (M3-C):**
    - 400: Validation errors (missing tenantId, message)
    - 500: Configuration errors (missing API keys) - checked before processing
    - 502: LLM provider failures (network, API errors)
    - 500: Other internal errors (database, unexpected exceptions with detailed error messages)
    
    **Logging & Observability (M3-E):**
    - All requests logged with structured metadata (tenant, user, scenario, metrics)
    - Errors logged with trace IDs for debugging
    - Token usage and latency metrics tracked
    - Logs stored in date-rotated files: logs/chat/chat.YYYY-MM-DD.log
    """
    # Generate trace ID for request tracking (US-AI-M3-E)
    trace_id = generate_trace_id()
    
    # Early validation: Check if required API keys are configured
    embedding_key = settings.OPENAI_API_KEY
    llm_key = settings.get_llm_api_key()
    
    if not embedding_key or embedding_key.strip() == "":
        log_chat_error(
            error_type="configuration",
            error_message="OpenAI API key for embeddings is not configured",
            tenant_id=request.tenantId,
            user_id=request.userId,
            scenario=request.scenario,
            trace_id=trace_id,
            exception=None
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "errorCode": "CONFIGURATION_ERROR",
                "message": "OpenAI API key is not configured. Please set OPENAI_API_KEY environment variable.",
                "details": {"missingConfig": "OPENAI_API_KEY"},
                "traceId": trace_id
            }
        )
    
    if not llm_key or llm_key.strip() == "":
        log_chat_error(
            error_type="configuration",
            error_message="LLM API key is not configured",
            tenant_id=request.tenantId,
            user_id=request.userId,
            scenario=request.scenario,
            trace_id=trace_id,
            exception=None
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "errorCode": "CONFIGURATION_ERROR",
                "message": "LLM API key is not configured. Please set LLM_API_KEY or OPENAI_API_KEY environment variable.",
                "details": {"missingConfig": "LLM_API_KEY"},
                "traceId": trace_id
            }
        )
    
    try:
        service = ChatService(db_session=db)
        result = await service.chat(request, trace_id=trace_id)
        return result
    
    except ChatValidationError as e:
        # Log structured validation error (US-AI-M3-E)
        log_chat_error(
            error_type="validation",
            error_message=str(e),
            tenant_id=request.tenantId,
            user_id=request.userId,
            scenario=request.scenario,
            trace_id=trace_id,
            exception=e
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorCode": "VALIDATION_ERROR",
                "message": str(e),
                "details": {"field": "request"},
                "traceId": trace_id
            }
        )
    
    except LLMProviderError as e:
        # Log structured LLM provider error (US-AI-M3-E)
        log_chat_error(
            error_type="llm_failure",
            error_message="LLM provider failed to generate response",
            tenant_id=request.tenantId,
            user_id=request.userId,
            scenario=request.scenario,
            trace_id=trace_id,
            exception=e,
            additional_context={"provider": "openai"}
        )
        
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "errorCode": "LLM_PROVIDER_ERROR",
                "message": "Failed to generate response from AI provider. Please try again.",
                "details": {"provider": "openai"},
                "traceId": trace_id
            }
        )
    
    except Exception as e:
        # Log structured unexpected error (US-AI-M3-E)
        log_chat_error(
            error_type="unexpected",
            error_message=str(e),
            tenant_id=request.tenantId,
            user_id=request.userId,
            scenario=request.scenario,
            trace_id=trace_id,
            exception=e
        )
        
        # Include error message in response for better debugging
        error_message = str(e)
        error_details = {"error": error_message}
        
        # Check if it's a configuration/API key related error
        if "api key" in error_message.lower() or "openai_api_key" in error_message.lower():
            error_details["hint"] = "Check that OPENAI_API_KEY and LLM_API_KEY environment variables are properly set"
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "errorCode": "INTERNAL_SERVER_ERROR",
                "message": error_message if error_message else "An unexpected error occurred while processing your request.",
                "details": error_details,
                "traceId": trace_id
            }
        )



