"""
Entry functions for running the Tutor LangGraph.

These functions provide the internal API for starting and continuing tutor sessions.
They are called by the HTTP endpoints in app/api/v1/tutor.py.
"""
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.tutor.graph_context import (
    TutorGraphContext,
    TutorStartParams,
    TutorContinueParams,
    TutorTurnResult
)
from app.tutor.graph import tutor_app
from app.tutor.thinking_trace import serialize_thinking_trace

logger = logging.getLogger(__name__)


async def run_tutor_start(
    params: TutorStartParams,
    session: AsyncSession,
    locale: Optional[str] = None,
    include_thinking_trace: bool = False,
) -> TutorTurnResult:
    """
    Start a new tutoring session.
    
    Args:
        params: TutorStartParams with lesson, objectives, student info
        session: AsyncSession for database operations
        locale: BCP-47 locale code (e.g. 'ar-JO', 'en-US'). Stored in session.
        include_thinking_trace: Whether to include thinking trace in result
        
    Returns:
        TutorTurnResult with session_id and first tutor reply
    """
    logger.info(
        f"Starting new tutor session: tenant={params.tenant_id}, "
        f"student={params.student_id}, lesson={params.lesson_id}, "
        f"locale={locale or params.locale or 'ar-JO'}"
    )
    
    # Determine locale (prefer explicit parameter, then params.locale, then default)
    effective_locale = locale or params.locale or "ar-JO"
    
    # Build initial context
    initial_state = TutorGraphContext(
        tenant_id=params.tenant_id,
        session_id=None,  # Will be created
        ou_id=params.ou_id,
        context_scopes=params.context_scopes,
        program_id=params.program_id,
        lesson_id=params.lesson_id,
        objective_ids=params.objective_ids,
        objective_labels=params.objective_labels,
        student_id=params.student_id,
        region_id=params.region_id,
        lesson_config=params.lesson_config,
        student_message=params.initial_student_message,
        db_session=session,  # Inject database session
        thinking_trace=[],  # Initialize empty trace
    )
    
    # Store locale in a way that graph nodes can access
    # This is a proper dataclass field so it survives LangGraph serialization
    initial_state.locale_hint = effective_locale
    
    # Invoke graph (returns dict, not dataclass)
    final_state = await tutor_app.ainvoke(initial_state)
    
    logger.info(
        f"Tutor start completed: session={final_state['session_id']}, "
        f"objective={final_state.get('current_objective_id')}, "
        f"complete={final_state.get('lesson_complete', False)}"
    )
    
    # Build thinking trace if requested
    thinking_trace = None
    if include_thinking_trace:
        raw_trace = final_state.get('thinking_trace', [])
        if raw_trace:
            # Serialize TutorThinkingStep objects to dicts
            thinking_trace = _serialize_trace(raw_trace)
    
    return TutorTurnResult(
        tenant_id=final_state['tenant_id'],
        session_id=final_state['session_id'],
        lesson_id=final_state['lesson_id'],
        current_objective_id=final_state.get('current_objective_id'),
        tutor_reply=final_state.get('tutor_reply') or "",
        lesson_complete=final_state.get('lesson_complete', False),
        thinking_trace=thinking_trace,
    )


async def run_tutor_turn(
    params: TutorContinueParams,
    session: AsyncSession,
    include_thinking_trace: bool = False,
) -> TutorTurnResult:
    """
    Continue an existing tutoring session.
    
    Args:
        params: TutorContinueParams with session_id and student message
        session: AsyncSession for database operations
        include_thinking_trace: Whether to include thinking trace in result
        
    Returns:
        TutorTurnResult with updated session state and tutor reply
    """
    logger.info(
        f"Continuing tutor session: tenant={params.tenant_id}, "
        f"session={params.session_id}"
    )
    
    # Build initial context (load_session_and_profile will populate the rest)
    initial_state = TutorGraphContext(
        tenant_id=params.tenant_id,
        session_id=params.session_id,
        lesson_id="",  # Will be loaded
        student_id="",  # Will be loaded
        student_message=params.student_message,
        db_session=session,  # Inject database session
        thinking_trace=[],  # Initialize empty trace
    )
    
    # Invoke graph (returns dict, not dataclass)
    final_state = await tutor_app.ainvoke(initial_state)
    
    logger.info(
        f"Tutor turn completed: session={final_state['session_id']}, "
        f"objective={final_state.get('current_objective_id')}, "
        f"complete={final_state.get('lesson_complete', False)}"
    )
    
    # Build thinking trace if requested
    thinking_trace = None
    if include_thinking_trace:
        raw_trace = final_state.get('thinking_trace', [])
        if raw_trace:
            thinking_trace = _serialize_trace(raw_trace)
    
    return TutorTurnResult(
        tenant_id=final_state['tenant_id'],
        session_id=final_state['session_id'],
        lesson_id=final_state['lesson_id'],
        current_objective_id=final_state.get('current_objective_id'),
        tutor_reply=final_state.get('tutor_reply') or "",
        lesson_complete=final_state.get('lesson_complete', False),
        thinking_trace=thinking_trace,
    )


def _serialize_trace(trace: List[Any]) -> List[Dict[str, Any]]:
    """
    Serialize thinking trace to JSON-safe format.
    
    Handles both TutorThinkingStep objects and plain dicts.
    """
    result = []
    for step in trace:
        if hasattr(step, 'to_dict'):
            result.append(step.to_dict())
        elif isinstance(step, dict):
            result.append(step)
        else:
            # Fallback: convert to string representation
            result.append({"stage": "unknown", "summary": str(step)})
    return result
