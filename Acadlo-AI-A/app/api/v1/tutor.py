"""
Tutor HTTP API Endpoints (US-AI-M4-G).

Exposes the Tutor Runtime Engine via versioned HTTP API for Nuxt/ABP integration.

Endpoints:
- POST /v1/tutor/start - Start a new tutor session
- POST /v1/tutor/turn - Continue an existing session

Architecture Notes:
- This API is stateless; all state is stored in the database.
- Multi-tenancy is explicit: tenant_id is required on all requests.
- Locale is stored in the session on /start and reused on /turn.
- The tutor engine is LLM-agnostic; provider details are hidden behind this API.

Integration Guide (for Nuxt/ABP):
1. Call POST /v1/tutor/start once per lesson to create a session.
2. Call POST /v1/tutor/turn for each student message.
3. Check lesson_complete to know when to show completion UI.
4. ABP propagates tenant_id and student_id from authenticated context.
5. The tutor service does not depend on ABP types; compatible IDs are passed via API.
"""
import logging
import re
import uuid
from typing import Dict, List, Set, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.schemas import (
    StartTutorSessionRequest,
    ContinueTutorSessionRequest,
    TutorTurnResponse,
    TutorErrorResponse,
    TutorErrorCodes,
)
from app.tutor.graph_context import TutorStartParams, TutorContinueParams
from app.tutor.runner import run_tutor_start, run_tutor_turn
from app.tutor.types import LessonTeachingConfig
from app.tutor.exceptions import TutorRuntimeError, ObjectiveStateNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tutor", tags=["Tutor"])


def _generate_request_id() -> str:
    """Generate a unique request ID for logging and correlation."""
    return str(uuid.uuid4())[:8]


def _slugify_objective_text(text: str, fallback_index: int) -> str:
    """
    Convert a plain-English objective into a stable, DB-safe objective_id.
    Max length is aligned with ObjectiveState.objective_id String(100).
    """
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    if not normalized:
        normalized = f"objective_{fallback_index}"
    objective_id = f"obj_{normalized}"
    return objective_id[:100]


def _resolve_objectives(body: StartTutorSessionRequest) -> Tuple[List[str], Dict[str, str]]:
    """
    Resolve objective IDs and labels from request body.
    Priority:
    1) objective_ids when provided
    2) plain-English objectives converted to generated IDs
    """
    if body.objective_ids:
        # Caller provided explicit IDs; we trust and use them as-is.
        return body.objective_ids, {}

    if not body.objectives:
        # Truly optional objectives: return empty and let onboarding / lesson
        # resolution decide what to do next.
        return [], {}

    labels: Dict[str, str] = {}
    resolved_ids: List[str] = []
    seen_ids: Set[str] = set()

    for index, text in enumerate(body.objectives, start=1):
        base_id = _slugify_objective_text(text, index)
        objective_id = base_id
        suffix = 2
        while objective_id in seen_ids:
            suffix_text = f"_{suffix}"
            objective_id = f"{base_id[:max(0, 100 - len(suffix_text))]}{suffix_text}"
            suffix += 1

        seen_ids.add(objective_id)
        resolved_ids.append(objective_id)
        labels[objective_id] = text

    return resolved_ids, labels


def _log_request(
    endpoint: str,
    tenant_id: str,
    session_id: str = None,
    request_id: str = None,
    extra: dict = None,
) -> None:
    """Log request metadata for debugging."""
    msg = f"[{request_id}] {endpoint}: tenant={tenant_id}"
    if session_id:
        msg += f", session={session_id}"
    if extra:
        for k, v in extra.items():
            msg += f", {k}={v}"
    logger.info(msg)


def _log_response(
    endpoint: str,
    request_id: str,
    status_code: int,
    session_id: str = None,
    lesson_complete: bool = None,
) -> None:
    """Log response metadata for debugging."""
    msg = f"[{request_id}] {endpoint} -> {status_code}"
    if session_id:
        msg += f", session={session_id}"
    if lesson_complete is not None:
        msg += f", complete={lesson_complete}"
    logger.info(msg)


@router.post(
    "/start",
    response_model=TutorTurnResponse,
    summary="Start a new tutor session",
    description="Start a new tutor session for a student on a specific lesson and objectives.",
    responses={
        200: {
            "description": "Session started successfully",
            "model": TutorTurnResponse,
        },
        400: {
            "description": "Validation error (missing fields, missing objectives input)",
            "model": TutorErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": TutorErrorResponse,
        },
    },
)
async def start_tutor_session(
    body: StartTutorSessionRequest,
    db: AsyncSession = Depends(get_session),
) -> TutorTurnResponse:
    """
    Start a new tutoring session.
    
    Creates a new TutorSession and runs the first turn of the tutor graph.
    Returns the initial tutor reply (greeting / first question).
    
    **Sequence:**
    1. Validates request fields.
    2. Creates TutorSession and ObjectiveState records.
    3. Runs the tutor thinking loop (analyze → plan → generate).
    4. Returns tutor reply and session ID.
    
    **Locale Handling:**
    - If locale is provided, it's stored in the session.
    - If null, defaults to 'ar-JO' (can be configured per tenant later).
    - All subsequent /turn calls use the stored locale.
    """
    request_id = _generate_request_id()
    
    _log_request(
        endpoint="tutor_start",
        tenant_id=body.tenant_id,
        request_id=request_id,
        extra={
            "student_id": body.student_id,
            "lesson_id": body.lesson_id,
            "objectives": len(body.objective_ids or body.objectives or []),
        },
    )
    
    try:
        # Build lesson config if provided (ensure lesson_id is set from body when missing)
        lesson_config = None
        if body.lesson_config:
            config_dict = dict(body.lesson_config)
            if "lesson_id" not in config_dict or config_dict["lesson_id"] is None:
                config_dict["lesson_id"] = body.lesson_id
            if "objective_configs" not in config_dict:
                config_dict["objective_configs"] = {}
            lesson_config = LessonTeachingConfig(**config_dict)
        
        if (body.lesson_id or "").strip().lower() == "pending" and not body.objective_ids and not body.objectives:
            objective_ids, objective_labels = [], {}
        else:
            objective_ids, objective_labels = _resolve_objectives(body)

        # Prepare params
        params = TutorStartParams(
            tenant_id=body.tenant_id,
            student_id=body.student_id,
            lesson_id=body.lesson_id,
            objective_ids=objective_ids,
            objective_labels=objective_labels,
            ou_id=body.ou_id,
            region_id=body.region_id,
            program_id=body.program_id,
            context_scopes=body.context_scopes,
            lesson_config=lesson_config,
            initial_student_message=body.initial_student_message,
        )
        
        # Store locale in session metadata (done by runner/graph node)
        # We pass it via a special mechanism until we add locale to TutorStartParams
        # For now, we'll inject it into db session context
        locale = body.locale or "ar-JO"
        
        # Run the tutor graph
        result = await run_tutor_start(
            params=params,
            session=db,
            locale=locale,
            include_thinking_trace=body.include_thinking_trace,
        )
        
        # Build response
        response = TutorTurnResponse(
            tenant_id=result.tenant_id,
            session_id=result.session_id,
            lesson_id=result.lesson_id,
            current_objective_id=result.current_objective_id,
            tutor_reply=result.tutor_reply,
            lesson_complete=result.lesson_complete,
        )
        
        # Include thinking trace if requested
        if body.include_thinking_trace and hasattr(result, 'thinking_trace'):
            response.debug = {
                "thinking_trace": result.thinking_trace,
                "request_id": request_id,
            }
        
        _log_response(
            endpoint="tutor_start",
            request_id=request_id,
            status_code=200,
            session_id=result.session_id,
            lesson_complete=result.lesson_complete,
        )
        
        return response
        
    except ValueError as e:
        # Validation errors from internal layers
        logger.warning(f"[{request_id}] tutor_start validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": TutorErrorCodes.VALIDATION_ERROR,
                "message": str(e),
                "details": {"request_id": request_id},
            },
        )
    
    except TutorRuntimeError as e:
        logger.error(f"[{request_id}] tutor_start runtime error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": TutorErrorCodes.INTERNAL_ERROR,
                "message": str(e),
                "details": {"request_id": request_id},
            },
        )
    
    except Exception as e:
        logger.error(f"[{request_id}] tutor_start unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": TutorErrorCodes.INTERNAL_ERROR,
                "message": "An unexpected error occurred while starting the tutor session.",
                "details": {"request_id": request_id, "error": str(e)},
            },
        )



@router.post(
    "/turn",
    response_model=TutorTurnResponse,
    summary="Continue a tutor session",
    description="Continue an existing tutor session with a new student message.",
    responses={
        200: {
            "description": "Turn completed successfully",
            "model": TutorTurnResponse,
        },
        400: {
            "description": "Validation error (empty message)",
            "model": TutorErrorResponse,
        },
        404: {
            "description": "Session not found",
            "model": TutorErrorResponse,
        },
        403: {
            "description": "Tenant mismatch (session belongs to different tenant)",
            "model": TutorErrorResponse,
        },
        409: {
            "description": "Session is terminal (lesson already complete)",
            "model": TutorErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": TutorErrorResponse,
        },
    },
)
async def continue_tutor_session(
    body: ContinueTutorSessionRequest,
    db: AsyncSession = Depends(get_session),
) -> TutorTurnResponse:
    """
    Continue an existing tutoring session.
    
    Loads the session, processes the student message, and returns the tutor reply.
    
    **Sequence:**
    1. Loads TutorSession by session_id.
    2. Validates tenant_id matches session tenant.
    3. Checks session is not terminal (lesson_complete).
    4. Runs the tutor thinking loop with student message.
    5. Returns updated tutor reply.
    
    **Locale Handling:**
    - Locale is read from the stored session, not from the request.
    - This ensures language consistency throughout the session.
    """
    request_id = _generate_request_id()
    
    _log_request(
        endpoint="tutor_turn",
        tenant_id=body.tenant_id,
        session_id=body.session_id,
        request_id=request_id,
    )
    
    try:
        # Prepare params
        params = TutorContinueParams(
            tenant_id=body.tenant_id,
            session_id=body.session_id,
            student_message=body.student_message,
        )
        
        # Run the tutor graph
        result = await run_tutor_turn(
            params=params,
            session=db,
            include_thinking_trace=body.include_thinking_trace,
        )
        
        # Build response
        response = TutorTurnResponse(
            tenant_id=result.tenant_id,
            session_id=result.session_id,
            lesson_id=result.lesson_id,
            current_objective_id=result.current_objective_id,
            tutor_reply=result.tutor_reply,
            lesson_complete=result.lesson_complete,
        )
        
        # Include thinking trace if requested
        if body.include_thinking_trace and hasattr(result, 'thinking_trace'):
            response.debug = {
                "thinking_trace": result.thinking_trace,
                "request_id": request_id,
            }
        
        _log_response(
            endpoint="tutor_turn",
            request_id=request_id,
            status_code=200,
            session_id=result.session_id,
            lesson_complete=result.lesson_complete,
        )
        
        return response
        
    except ObjectiveStateNotFoundError as e:
        # Session or objective not found
        logger.warning(f"[{request_id}] tutor_turn session not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": TutorErrorCodes.SESSION_NOT_FOUND,
                "message": f"Session not found: {body.session_id}",
                "details": {"request_id": request_id},
            },
        )
    
    except ValueError as e:
        error_msg = str(e).lower()
        
        # Check for tenant mismatch
        if "tenant" in error_msg and "mismatch" in error_msg:
            logger.warning(f"[{request_id}] tutor_turn tenant mismatch: {e}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": TutorErrorCodes.TENANT_MISMATCH,
                    "message": "Session belongs to a different tenant.",
                    "details": {"request_id": request_id},
                },
            )
        
        # Check for terminal session
        if "complete" in error_msg or "terminal" in error_msg:
            logger.warning(f"[{request_id}] tutor_turn session terminal: {e}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": TutorErrorCodes.SESSION_TERMINAL,
                    "message": "Session is already complete and cannot accept new turns.",
                    "details": {"request_id": request_id},
                },
            )
        
        # General validation error
        logger.warning(f"[{request_id}] tutor_turn validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": TutorErrorCodes.VALIDATION_ERROR,
                "message": str(e),
                "details": {"request_id": request_id},
            },
        )
    
    except TutorRuntimeError as e:
        logger.error(f"[{request_id}] tutor_turn runtime error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": TutorErrorCodes.INTERNAL_ERROR,
                "message": str(e),
                "details": {"request_id": request_id},
            },
        )
    
    except Exception as e:
        logger.error(f"[{request_id}] tutor_turn unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": TutorErrorCodes.INTERNAL_ERROR,
                "message": "An unexpected error occurred while processing the tutor turn.",
                "details": {"request_id": request_id, "error": str(e)},
            },
        )
