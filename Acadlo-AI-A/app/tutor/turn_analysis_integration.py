"""
Integration helpers for turn analysis in LangGraph.

This module provides utilities to combine turn analysis and snapshot updates
for use in LangGraph nodes.
"""
import logging
from typing import Tuple, Optional

from app.tutor.graph_context import TutorGraphContext
from app.tutor.enums import AffectSignal
from app.tutor.turn_analysis_types import StudentTurnAnalysis
from app.tutor.turn_analysis_service import analyze_student_turn
from app.tutor.types import ObjectivePerformanceSnapshot
from app.tutor.performance_snapshot import (
    update_performance_snapshot,
    build_initial_performance_snapshot
)
from app.tutor.exceptions import MissingContextError

logger = logging.getLogger(__name__)


async def analyze_turn_and_update_snapshot(
    state: TutorGraphContext,
) -> Tuple[StudentTurnAnalysis, ObjectivePerformanceSnapshot]:
    """
    Analyze student turn and update performance snapshot.
    
    This is a convenience function for LangGraph nodes that combines:
    1. Analyzing the student's message using LLM
    2. Building/updating the ObjectivePerformanceSnapshot
    
    Args:
        state: TutorGraphContext with student_message and current session/objective data
        
    Returns:
        Tuple of (StudentTurnAnalysis, updated ObjectivePerformanceSnapshot)
        
    Raises:
        MissingContextError: If required context is missing
    """
    if not state.student_message:
        raise MissingContextError("student_message", "student_message is required for turn analysis")
    
    if not state.current_objective_id:
        raise MissingContextError("current_objective_id", "current_objective_id is required for turn analysis")
    
    # Get current objective state
    current_obj_state = state.objectives.get(state.current_objective_id)
    if not current_obj_state:
        raise MissingContextError(
            "objectives",
            f"ObjectiveState not found for {state.current_objective_id}"
        )
    
    # Determine locale from session
    locale = "en-US"  # Default
    if state.session and state.session.session_metadata:
        metadata = state.session.session_metadata
        locale = metadata.get("locale") or metadata.get("language") or "en-US"
    
    # Analyze the student's turn
    analysis = await analyze_student_turn(
        tenant_id=state.tenant_id,
        student_message=state.student_message,
        locale=locale,
        expected_answer=None,  # TODO: Get from current question context (future)
        objective_id=state.current_objective_id,
        lesson_id=state.lesson_id,
        chat_history=state.chat_history,
    )
    
    logger.info(
        f"Turn analysis: session={state.session_id}, objective={state.current_objective_id}, "
        f"kind={analysis.kind.value}, correctness={analysis.correctness.value}"
    )
    
    # Build previous snapshot from current ObjectiveState
    previous_snapshot = build_snapshot_from_objective_state(current_obj_state)
    
    # Update snapshot with new analysis
    updated_snapshot = update_performance_snapshot(
        previous=previous_snapshot,
        analysis=analysis,
        max_recent=10
    )
    
    return analysis, updated_snapshot


def build_snapshot_from_objective_state(obj_state) -> ObjectivePerformanceSnapshot:
    """
    Build ObjectivePerformanceSnapshot from an ObjectiveState model.
    
    This is a helper to convert persisted ObjectiveState data into
    the snapshot format used by the state machine.
    
    Args:
        obj_state: ObjectiveState ORM model
        
    Returns:
        ObjectivePerformanceSnapshot
    """
    # Extract recent answers from extra field if available
    recent_answers = []
    if obj_state.extra and "recent_answers" in obj_state.extra:
        recent_answers = obj_state.extra["recent_answers"]
    
    # Extract recent affect from extra field if available
    # Parse stored string value back into AffectSignal enum
    recent_affect: Optional[AffectSignal] = None
    if obj_state.extra and "recent_affect" in obj_state.extra:
        stored_affect = obj_state.extra["recent_affect"]
        if stored_affect:
            try:
                recent_affect = AffectSignal(stored_affect)
            except ValueError:
                # Invalid stored value, log and leave as None
                logger.warning(
                    f"Invalid AffectSignal value in storage: '{stored_affect}', "
                    f"falling back to None"
                )
                recent_affect = None
    
    return ObjectivePerformanceSnapshot(
        total_attempts=obj_state.questions_asked,
        correct_attempts=obj_state.questions_correct,
        incorrect_attempts=obj_state.questions_incorrect,
        recent_answers=recent_answers,
        recent_affect=recent_affect
    )


def persist_snapshot_to_state(obj_state, snapshot: ObjectivePerformanceSnapshot) -> None:
    """
    Persist ObjectivePerformanceSnapshot data back to ObjectiveState model.
    
    Updates the ORM model in-place.
    Converts AffectSignal enum to string for JSONB storage.
    
    Args:
        obj_state: ObjectiveState ORM model
        snapshot: ObjectivePerformanceSnapshot to persist
    """
    obj_state.questions_asked = snapshot.total_attempts
    obj_state.questions_correct = snapshot.correct_attempts
    obj_state.questions_incorrect = snapshot.incorrect_attempts
    
    # Store recent data in extra field
    if not obj_state.extra:
        obj_state.extra = {}
    
    obj_state.extra["recent_answers"] = snapshot.recent_answers
    
    # Store recent_affect as string value for JSONB
    if snapshot.recent_affect is not None:
        obj_state.extra["recent_affect"] = snapshot.recent_affect.value
    else:
        obj_state.extra["recent_affect"] = None
