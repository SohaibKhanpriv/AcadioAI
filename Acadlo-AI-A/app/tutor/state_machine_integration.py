"""
Integration between the state machine and ObjectiveState persistence.

This module provides helpers to apply state transitions to persisted ObjectiveState records.
"""
from typing import Protocol
from dataclasses import dataclass

from app.db.models import ObjectiveState as ObjectiveStateModel
from app.tutor.enums import ObjectiveTeachingState
from app.tutor.types import (
    ObjectivePerformanceSnapshot,
    ObjectiveTeachingConfig,
    ObjectiveStateTransitionInput
)
from app.tutor.state_machine import compute_objective_state_transition


class ObjectiveStateRepo(Protocol):
    """
    Protocol for ObjectiveState repository.
    
    This allows the integration to work with any repository implementation
    without coupling to the specific implementation.
    """
    async def get_objective_state(
        self, tenant_id: str, session_id: str, objective_id: str
    ) -> ObjectiveStateModel:
        ...
    
    async def save_objective_state(
        self, state: ObjectiveStateModel
    ) -> None:
        ...


@dataclass
class ApplyObjectiveTransitionArgs:
    """Arguments for applying a state transition"""
    tenant_id: str
    session_id: str
    objective_id: str
    performance: ObjectivePerformanceSnapshot
    objective_config: ObjectiveTeachingConfig


async def apply_objective_state_transition(
    repo: ObjectiveStateRepo,
    args: ApplyObjectiveTransitionArgs
) -> ObjectiveStateModel:
    """
    Load ObjectiveState, compute transition, update, and save.
    
    This is the integration point between the pure state machine
    and the persistence layer.
    
    Args:
        repo: Repository for loading/saving ObjectiveState
        args: Contains tenant_id, session_id, objective_id, performance, config
        
    Returns:
        Updated ObjectiveStateModel
        
    Raises:
        Exception: If ObjectiveState not found
    """
    # Load current state from database
    state_model = await repo.get_objective_state(
        tenant_id=args.tenant_id,
        session_id=args.session_id,
        objective_id=args.objective_id
    )
    
    if not state_model:
        raise Exception(
            f"ObjectiveState not found: tenant={args.tenant_id}, "
            f"session={args.session_id}, objective={args.objective_id}"
        )
    
    # Build input for state machine
    transition_input = ObjectiveStateTransitionInput(
        current_state=ObjectiveTeachingState(state_model.state),
        objective_config=args.objective_config,
        performance=args.performance
    )
    
    # Compute transition (pure function, no side effects)
    result = compute_objective_state_transition(transition_input)
    
    # Update ORM model with transition result
    state_model.state = result.next_state.value
    state_model.mastery_estimate = result.mastery_estimate.value
    
    # Update counters from performance
    state_model.questions_asked = args.performance.total_attempts
    state_model.questions_correct = args.performance.correct_attempts
    state_model.questions_incorrect = args.performance.incorrect_attempts
    
    # Extract recent error types
    error_types = []
    for ans in args.performance.recent_answers:
        if not ans.get("correct", False) and "error_type" in ans:
            error_types.append(ans["error_type"])
    state_model.last_error_types = error_types[-5:]  # Keep last 5
    
    # Set mastered_at timestamp if transitioning to MASTERED for first time
    if result.next_state == ObjectiveTeachingState.MASTERED:
        if state_model.mastered_at is None:
            from datetime import datetime
            state_model.mastered_at = datetime.utcnow()
    
    # Set started_at if this is first transition from NOT_STARTED
    if state_model.started_at is None:
        if result.next_state != ObjectiveTeachingState.NOT_STARTED:
            from datetime import datetime
            state_model.started_at = datetime.utcnow()
    
    # Save to database
    await repo.save_objective_state(state_model)
    
    return state_model


def build_performance_snapshot_from_state(
    state: ObjectiveStateModel,
    recent_answers: list = None
) -> ObjectivePerformanceSnapshot:
    """
    Helper to build a ObjectivePerformanceSnapshot from an ObjectiveState model.
    
    Useful when you have a state loaded from DB and need to build the snapshot.
    
    Args:
        state: ObjectiveState ORM model
        recent_answers: Optional list of recent answer dicts
        
    Returns:
        ObjectivePerformanceSnapshot
    """
    return ObjectivePerformanceSnapshot(
        total_attempts=state.questions_asked,
        correct_attempts=state.questions_correct,
        incorrect_attempts=state.questions_incorrect,
        recent_answers=recent_answers or [],
        recent_affect=None  # TODO: Future - extract from state.extra if available
    )

