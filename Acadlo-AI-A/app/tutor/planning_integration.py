"""
Planning Integration for LangGraph.

This module provides helpers to integrate the tutor planning layer
with LangGraph nodes and the TutorGraphContext.
"""
import logging
from typing import Optional

from app.tutor.graph_context import TutorGraphContext
from app.tutor.enums import ObjectiveTeachingState
from app.tutor.types import (
    ObjectivePerformanceSnapshot,
    ObjectiveTeachingConfig,
)
from app.tutor.turn_analysis_types import StudentTurnAnalysis
from app.tutor.action_schema import TutorActionPlan, TutorActionKind
from app.tutor.planning import plan_next_tutor_action
from app.tutor.exceptions import MissingContextError

logger = logging.getLogger(__name__)


def plan_for_current_turn(
    *,
    state: TutorGraphContext,
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
) -> TutorActionPlan:
    """
    Plan the next tutor action for the current turn.
    
    This is a convenience function for LangGraph nodes that:
    1. Reads current objective teaching state from state.objectives[state.current_objective_id]
    2. Reads ObjectiveTeachingConfig from state.objective_config (or creates default)
    3. Delegates to plan_next_tutor_action(...)
    4. Returns a TutorActionPlan
    
    Args:
        state: TutorGraphContext with session and objective data
        performance: Current ObjectivePerformanceSnapshot
        analysis: StudentTurnAnalysis from the analysis step
        
    Returns:
        TutorActionPlan specifying what the tutor should do next
        
    Raises:
        MissingContextError: If required context is missing
    """
    # Validate required context
    if not state.current_objective_id:
        raise MissingContextError(
            "current_objective_id",
            "current_objective_id is required for planning"
        )
    
    # Get current objective state
    current_obj_state = state.objectives.get(state.current_objective_id)
    if not current_obj_state:
        raise MissingContextError(
            "objectives",
            f"ObjectiveState not found for {state.current_objective_id}"
        )
    
    # Get teaching state from objective
    try:
        teaching_state = ObjectiveTeachingState(current_obj_state.state)
    except ValueError:
        logger.warning(
            f"Unknown teaching state '{current_obj_state.state}', "
            f"defaulting to NOT_STARTED"
        )
        teaching_state = ObjectiveTeachingState.NOT_STARTED
    
    # Get objective config (use provided or create default)
    config = _get_objective_config(state, state.current_objective_id)

    mcq_mode = False
    if state.session and state.session.session_metadata:
        mcq_mode = bool(state.session.session_metadata.get("mcq_mode", False))
    
    # Delegate to the pure planning function
    plan = plan_next_tutor_action(
        teaching_state=teaching_state,
        performance=performance,
        analysis=analysis,
        config=config,
        no_answer_streak=state.no_answer_streak,
        low_confidence=state.low_confidence,
        progress_evaluation=state.progress_evaluation,
        mcq_mode=mcq_mode,
    )
    
    logger.info(
        f"Planned action: session={state.session_id}, "
        f"objective={state.current_objective_id}, "
        f"teaching_state={teaching_state.value}, "
        f"action={plan.kind.value}, intent={plan.intent_label}"
    )
    
    return plan


def _get_objective_config(
    state: TutorGraphContext,
    objective_id: str,
) -> ObjectiveTeachingConfig:
    """
    Get the teaching configuration for an objective.
    
    Checks state.lesson_config first, then state.objective_config,
    finally returns a default config if neither is available.
    """
    # Try lesson config first (has configs for all objectives)
    if state.lesson_config:
        return state.lesson_config.get_config(objective_id)
    
    # Try direct objective config
    if state.objective_config and state.objective_config.objective_id == objective_id:
        return state.objective_config
    
    # Return default config
    return ObjectiveTeachingConfig(objective_id=objective_id)


def get_default_start_plan(objective_id: str) -> TutorActionPlan:
    """
    Get a default plan for starting a new objective.
    
    Used when there's no student message yet (lesson start).
    
    Args:
        objective_id: The objective being started
        
    Returns:
        TutorActionPlan for introducing the objective
    """
    return TutorActionPlan(
        kind=TutorActionKind.ASK_QUESTION,
        target_objective_id=objective_id,
        intent_label="diagnostic_question",
        metadata={"is_initial_turn": True},
    )


def should_end_lesson(
    state: TutorGraphContext,
    current_plan: TutorActionPlan,
) -> bool:
    """
    Determine if the lesson should end based on current state and plan.
    
    Returns True if:
    - Plan is END_LESSON
    - All objectives are mastered or escalated
    - Plan is SWITCH_OBJECTIVE but no more objectives available
    """
    if current_plan.kind == TutorActionKind.END_LESSON:
        return True
    
    if current_plan.kind == TutorActionKind.SWITCH_OBJECTIVE:
        # Check if there are remaining non-mastered, non-escalated objectives
        for obj_id, obj_state in state.objectives.items():
            if obj_state.state not in [
                ObjectiveTeachingState.MASTERED.value,
                ObjectiveTeachingState.ESCALATE.value,
            ]:
                return False
        # All objectives done
        return True
    
    return False


def get_next_objective_id(
    state: TutorGraphContext,
    current_objective_id: str,
) -> Optional[str]:
    """
    Get the next objective to work on after the current one.
    
    Returns the first objective that is not MASTERED or ESCALATE,
    or None if all objectives are done.
    """
    # Find objectives in order that aren't done
    for obj_id in state.objective_ids:
        if obj_id == current_objective_id:
            continue
        
        obj_state = state.objectives.get(obj_id)
        if not obj_state:
            # Objective not yet started
            return obj_id
        
        if obj_state.state not in [
            ObjectiveTeachingState.MASTERED.value,
            ObjectiveTeachingState.ESCALATE.value,
        ]:
            return obj_id
    
    return None

