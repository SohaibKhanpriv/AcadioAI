"""Pydantic schemas for all API requests and responses"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


# ============================================================================
# Common Types
# ============================================================================

class Visibility(BaseModel):
    """Visibility control for documents and chunks"""
    roles: List[str] = Field(..., description="List of roles that can access this resource", example=["Teacher", "Principal"])
    scopes: List[str] = Field(..., description="List of scopes (School:123, Directorate:5)", example=["School:123", "Directorate:5"])

    class Config:
        json_schema_extra = {
            "example": {
                "roles": ["Teacher", "Principal"],
                "scopes": ["School:123", "Directorate:5"]
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response for all endpoints"""
    errorCode: str = Field(..., description="Error code identifier", example="VALIDATION_ERROR")
    message: str = Field(..., description="Human readable error message", example="Invalid request payload")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    traceId: Optional[str] = Field(None, description="Optional correlation ID for tracing", example="trace-123-456")

    class Config:
        json_schema_extra = {
            "example": {
                "errorCode": "VALIDATION_ERROR",
                "message": "Invalid request payload",
                "details": {
                    "fieldErrors": {
                        "tenantId": "Field is required"
                    }
                },
                "traceId": "trace-123-456"
            }
        }


# ============================================================================
# Health & Echo
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Service health status", example="ok")
    service: str = Field(..., description="Service name", example="acadlo-ai-core")
    version: str = Field(..., description="Service version", example="0.1.0")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "service": "acadlo-ai-core",
                "version": "0.1.0"
            }
        }


class EchoRequest(BaseModel):
    """Echo endpoint request - accepts any JSON"""
    data: Dict[str, Any] = Field(..., description="Any JSON payload to echo back")

    class Config:
        json_schema_extra = {
            "example": {
                "data": {
                    "message": "Hello, World!",
                    "timestamp": "2025-11-22T10:00:00Z"
                }
            }
        }


class EchoResponse(BaseModel):
    """Echo endpoint response"""
    echo: Dict[str, Any] = Field(..., description="The echoed data from request")

    class Config:
        json_schema_extra = {
            "example": {
                "echo": {
                    "message": "Hello, World!",
                    "timestamp": "2025-11-22T10:00:00Z"
                }
            }
        }


# ============================================================================
# Document Ingestion
# ============================================================================

class ContentPayload(BaseModel):
    """Content payload for document ingestion"""
    type: Literal["text", "url"] = Field(..., description="Content type: text or url", example="text")
    value: str = Field(..., description="Full text content OR file URL", example="This is the full policy document text...")

    class Config:
        json_schema_extra = {
            "example": {
                "type": "text",
                "value": "This is the full policy document text..."
            }
        }


class DocumentIngestRequest(BaseModel):
    """Request schema for document ingestion"""
    tenantId: str = Field(..., description="Tenant identifier", example="t_abc")
    externalId: Optional[str] = Field(None, description="Optional link to ABP or other external system", example="Policy:42")
    title: str = Field(..., description="Document title", example="Transfer Policy")
    language: str = Field(..., description="Document language code", example="ar-JO")
    sourceType: str = Field(..., description="Source type of document", example="policy")
    visibility: Visibility = Field(..., description="Visibility and access control settings")
    tags: Dict[str, str] = Field(default_factory=dict, description="Document metadata tags", example={"stage": "Primary", "year": "2025"})
    content: ContentPayload = Field(..., description="Document content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata", example={"uploadedBy": "u_999", "sourceName": "policy-2025.pdf"})

    class Config:
        json_schema_extra = {
            "example": {
                "tenantId": "t_abc",
                "externalId": "Policy:42",
                "title": "Transfer Policy",
                "language": "ar-JO",
                "sourceType": "policy",
                "visibility": {
                    "roles": ["Principal", "Admin"],
                    "scopes": ["School:123"]
                },
                "tags": {
                    "stage": "Primary",
                    "year": "2025"
                },
                "content": {
                    "type": "text",
                    "value": "Full text content of the transfer policy document. This explains the procedures and requirements for transferring students between schools..."
                },
                "metadata": {
                    "uploadedBy": "u_999",
                    "sourceName": "policy-2025.pdf"
                }
            }
        }


class IngestionJobResponse(BaseModel):
    """Response after submitting a document for ingestion"""
    jobId: str = Field(..., description="Unique job identifier", example="job_123")
    status: Literal["pending", "processing", "completed", "failed"] = Field(..., description="Current job status", example="pending")

    class Config:
        json_schema_extra = {
            "example": {
                "jobId": "job_123",
                "status": "pending"
            }
        }


class IngestionJobStatusResponse(BaseModel):
    """Detailed job status response"""
    jobId: str = Field(..., description="Unique job identifier", example="job_123")
    tenantId: str = Field(..., description="Tenant identifier", example="t_abc")
    documentId: Optional[str] = Field(None, description="Document ID (if created)", example="doc_123")
    externalId: Optional[str] = Field(None, description="External ID from original request", example="Policy:42")
    status: Literal["pending", "processing", "completed", "failed"] = Field(..., description="Current job status", example="completed")
    errorMessage: Optional[str] = Field(None, description="Error message if failed")
    createdAt: datetime = Field(..., description="Job creation timestamp")
    updatedAt: datetime = Field(..., description="Last update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "jobId": "job_123",
                "tenantId": "t_abc",
                "documentId": "doc_123",
                "externalId": "Policy:42",
                "status": "completed",
                "errorMessage": None,
                "createdAt": "2025-11-18T10:00:00Z",
                "updatedAt": "2025-11-18T10:00:05Z"
            }
        }


# ============================================================================
# Search
# ============================================================================

class SearchFilters(BaseModel):
    """Filters for search requests"""
    sourceType: Optional[List[str]] = Field(None, description="Filter by source types", example=["policy"])
    subject: Optional[str] = Field(None, description="Filter by subject")
    grade: Optional[str] = Field(None, description="Filter by grade level")
    tags: Optional[Dict[str, str]] = Field(None, description="Filter by tags (must match all key-value pairs)", example={"year": "2021", "stage": "secondary"})

    class Config:
        json_schema_extra = {
            "example": {
                "sourceType": ["policy"],
                "subject": None,
                "grade": None,
                "tags": {"year": "2021", "stage": "secondary"}
            }
        }


class SearchRequest(BaseModel):
    """Search request schema"""
    tenantId: str = Field(..., description="Tenant identifier", example="t_abc")
    userId: str = Field(..., description="User identifier", example="u_999")
    roles: List[str] = Field(default_factory=list, description="User roles for access control", example=["Teacher"])
    language: str = Field(..., description="Query language code", example="ar-JO")
    query: str = Field(..., description="Search query text", example="what is the policy for student transfers?")
    filters: Optional[SearchFilters] = Field(None, description="Optional search filters")
    topK: int = Field(8, description="Number of top results to return", ge=1, le=100)

    class Config:
        json_schema_extra = {
            "example": {
                "tenantId": "t_abc",
                "userId": "u_999",
                "roles": ["Teacher"],
                "language": "ar-JO",
                "query": "what is the policy for student transfers?",
                "filters": {
                    "sourceType": ["policy"],
                    "subject": None,
                    "grade": None
                },
                "topK": 8
            }
        }


class SearchResultItem(BaseModel):
    """Individual search result item"""
    chunkId: str = Field(..., description="Chunk identifier", example="chunk_987")
    documentId: str = Field(..., description="Parent document identifier", example="doc_123")
    text: str = Field(..., description="Chunk text content", example="The policy for student transfers requires...")
    score: float = Field(..., description="Relevance score", ge=0.0, le=1.0, example=0.89)
    title: str = Field(..., description="Document title", example="Transfer Policy")
    tags: Dict[str, str] = Field(default_factory=dict, description="Document tags", example={"stage": "Primary"})

    class Config:
        json_schema_extra = {
            "example": {
                "chunkId": "chunk_987",
                "documentId": "doc_123",
                "text": "The policy for student transfers requires approval from both the sending and receiving school principals. The student must meet academic requirements...",
                "score": 0.89,
                "title": "Transfer Policy",
                "tags": {
                    "stage": "Primary"
                }
            }
        }


class SearchResponse(BaseModel):
    """Search response schema"""
    results: List[SearchResultItem] = Field(..., description="List of search results")

    class Config:
        json_schema_extra = {
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


# ============================================================================
# Chat
# ============================================================================

class ChatHistoryMessage(BaseModel):
    """Single chat history message"""
    role: Literal["user", "assistant"] = Field(..., description="Message role", example="user")
    content: str = Field(..., description="Message content", example="What is the transfer policy?")

    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "What is the transfer policy?"
            }
        }


class ChatRequest(BaseModel):
    """Chat request schema"""
    tenantId: str = Field(..., description="Tenant identifier", example="t_abc")
    userId: str = Field(..., description="User identifier", example="u_999")
    roles: List[str] = Field(default_factory=list, description="User roles for access control", example=["Owner"])
    language: str = Field(..., description="Conversation language code", example="ar-JO")
    scenario: str = Field("generic", description="Scenario hint for RAG", example="generic")
    sessionId: Optional[str] = Field(None, description="Session ID for multi-turn conversations", example="sess_123")
    message: str = Field(..., description="User message/question", example="How do I transfer a student?")
    history: List[ChatHistoryMessage] = Field(default_factory=list, description="Conversation history (optional)")
    uiContext: Optional[Dict[str, Any]] = Field(None, description="UI context information", example={"page": "policy-center"})

    class Config:
        json_schema_extra = {
            "example": {
                "tenantId": "t_abc",
                "userId": "u_999",
                "roles": ["Owner"],
                "language": "ar-JO",
                "scenario": "generic",
                "sessionId": "sess_123",
                "message": "How do I transfer a student?",
                "history": [
                    {
                        "role": "user",
                        "content": "Tell me about school policies"
                    },
                    {
                        "role": "assistant",
                        "content": "Our school has several important policies covering transfers, attendance, and conduct..."
                    }
                ],
                "uiContext": {
                    "page": "policy-center"
                }
            }
        }


class ChatCitation(BaseModel):
    """Citation/source for chat response"""
    documentId: str = Field(..., description="Source document ID", example="doc_123")
    chunkId: str = Field(..., description="Source chunk ID", example="chunk_987")
    title: str = Field(..., description="Document title", example="Student Transfer Policy")

    class Config:
        json_schema_extra = {
            "example": {
                "documentId": "doc_123",
                "chunkId": "chunk_987",
                "title": "Student Transfer Policy"
            }
        }


class ChatMetadata(BaseModel):
    """Metadata about the chat response"""
    model: Optional[str] = Field(None, description="LLM model used", example="gpt-4o-mini")
    retrievedChunks: Optional[int] = Field(None, description="Number of chunks retrieved from search", example=8)
    usedChunks: Optional[int] = Field(None, description="Number of chunks included in context", example=4)
    promptTokens: Optional[int] = Field(None, description="Tokens used in prompt", example=800)
    completionTokens: Optional[int] = Field(None, description="Tokens used in completion", example=150)
    totalTokens: Optional[int] = Field(None, description="Total tokens used", example=950)
    latencyMs: Optional[int] = Field(None, description="Response latency in milliseconds", example=2300)
    intent: Optional[str] = Field(None, description="Detected intent (deprecated, for compatibility)", example="Policy_QA")

    class Config:
        json_schema_extra = {
            "example": {
                "model": "gpt-4o-mini",
                "retrievedChunks": 8,
                "usedChunks": 4,
                "promptTokens": 800,
                "completionTokens": 150,
                "totalTokens": 950,
                "latencyMs": 2300,
                "intent": "Policy_QA"
            }
        }


class ChatResponse(BaseModel):
    """Chat response schema"""
    sessionId: Optional[str] = Field(None, description="Session identifier", example="sess_123")
    answer: str = Field(..., description="AI-generated answer", example="لنقل الطالب من صف إلى آخر، يجب اتباع الخطوات التالية...")
    language: str = Field(..., description="Response language code", example="ar-JO")
    citations: List[ChatCitation] = Field(default_factory=list, description="Source citations")
    meta: Optional[ChatMetadata] = Field(None, description="Response metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "sessionId": "sess_123",
                "answer": "لنقل الطالب من صف إلى آخر، يجب اتباع الخطوات التالية: 1) الحصول على موافقة مدير المدرسة الحالية، 2) التأكد من توفر مقعد في المدرسة المستهدفة...",
                "language": "ar-JO",
                "citations": [
                    {
                        "documentId": "doc_123",
                        "chunkId": "chunk_987",
                        "title": "Student Transfer Policy"
                    }
                ],
                "meta": {
                    "intent": "Policy_QA",
                    "tokens": 1234,
                    "latencyMs": 2300
                }
            }
        }


# ============================================================================
# Tutor
# ============================================================================

from pydantic import field_validator, model_validator


class StartTutorSessionRequest(BaseModel):
    """Request body for POST /v1/tutor/start"""
    tenant_id: str = Field(..., min_length=1, description="Tenant identifier")
    student_id: str = Field(..., min_length=1, description="Student identifier")
    lesson_id: Optional[str] = Field(
        default="pending",
        description="Lesson identifier. Use 'pending' or null for open-ended sessions.",
    )
    objective_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional objective IDs to cover. If omitted, provide `objectives`.",
    )
    objectives: Optional[List[str]] = Field(
        default=None,
        description="Optional plain-English objectives. Used when `objective_ids` is omitted.",
    )
    ou_id: Optional[str] = Field(None, description="Organization unit ID")
    region_id: Optional[str] = Field(None, description="Region code")
    program_id: Optional[str] = Field(None, description="Program ID")
    context_scopes: List[str] = Field(default_factory=list, description="RAG visibility scopes")
    locale: Optional[str] = Field(None, description="Locale (BCP-47, e.g. 'ar-JO', 'en-US')")
    initial_student_message: Optional[str] = Field(None, description="Optional first message")
    lesson_config: Optional[Dict[str, Any]] = Field(None, description="Lesson teaching config")
    include_thinking_trace: bool = Field(default=False, description="Include thinking trace in debug")

    @field_validator('objective_ids', 'objectives')
    @classmethod
    def normalize_objective_lists(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        normalized = [item.strip() for item in v if item and item.strip()]
        return normalized or None

    @model_validator(mode="after")
    def validate_objectives_inputs(self):
        """
        Keep lesson_id / objectives flexible at the API layer.

        - If lesson_id is null/empty, normalise it to 'pending' (open-ended session).
        - When lesson_id is provided with objective_ids/objectives, we use them.
        - When objectives are omitted, we allow onboarding + lesson resolution
          to decide what to do instead of raising validation errors.
        """
        # Normalise lesson_id
        if not self.lesson_id or not str(self.lesson_id).strip():
            self.lesson_id = "pending"
        return self


class ContinueTutorSessionRequest(BaseModel):
    """Request body for POST /v1/tutor/turn"""
    tenant_id: str = Field(..., min_length=1, description="Tenant identifier")
    session_id: str = Field(..., min_length=1, description="Session ID")
    student_message: str = Field(..., min_length=1, description="Student message")
    include_thinking_trace: bool = Field(default=False, description="Include thinking trace in debug")


class TutorTurnResponse(BaseModel):
    """Response for /v1/tutor/start and /v1/tutor/turn"""
    tenant_id: str = Field(..., description="Tenant identifier")
    session_id: str = Field(..., description="Session identifier")
    lesson_id: str = Field(..., description="Lesson identifier")
    current_objective_id: Optional[str] = Field(None, description="Current objective ID")
    tutor_reply: str = Field(..., description="Tutor's response text")
    lesson_complete: bool = Field(default=False, description="Whether lesson is complete")
    debug: Optional[Dict[str, Any]] = Field(None, description="Debug info including thinking_trace")


class TutorErrorResponse(BaseModel):
    """Error response for tutor API"""
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class TutorErrorCodes:
    """Error codes for tutor API"""
    VALIDATION_ERROR = "validation_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_TERMINAL = "session_terminal"
    TENANT_MISMATCH = "tenant_mismatch"
    INTERNAL_ERROR = "internal_error"

