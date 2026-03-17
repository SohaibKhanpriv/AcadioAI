"""
Objective Teaching State Machine.

This module implements the pedagogical state machine that governs how the tutor
progresses a student through a single learning objective.

The state machine is:
- Pure (no side effects, no DB/LLM calls)
- Deterministic (same input always produces same output)
- Rule-based (no ML/AI, just configurable thresholds)
"""
from app.tutor.enums import ObjectiveTeachingState, MasteryEstimate
from app.tutor.types import (
    ObjectiveStateTransitionInput,
    ObjectiveStateTransitionOutput,
    ObjectivePerformanceSnapshot,
    ObjectiveTeachingConfig,
    DEFAULT_TUTOR_BEHAVIOR_CONFIG,
)


def compute_objective_state_transition(
    input: ObjectiveStateTransitionInput
) -> ObjectiveStateTransitionOutput:
    """
    Compute the next teaching state based on current state and performance.
    
    This is a pure, deterministic function with no side effects.
    It can be unit tested thoroughly and used from LangGraph nodes.
    
    Args:
        input: Contains current_state, objective_config, performance
        
    Returns:
        Output with next_state, mastery_estimate, escalate_flag, reasoning
    """
    state = input.current_state
    config = input.objective_config
    perf = input.performance
    behavior_cfg = DEFAULT_TUTOR_BEHAVIOR_CONFIG

    # ===== FAST-TRACK: consecutive streak overrides =====
    # 5 correct in a row → MASTERED (student clearly gets it)
    if perf.consecutive_correct >= behavior_cfg.consecutive_correct_for_mastery:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.MASTERED,
            mastery_estimate=MasteryEstimate.HIGH,
            escalate_flag=False,
            reasoning=f"Fast-track mastery: {perf.consecutive_correct} consecutive correct answers"
        )

    # 5 wrong in a row → ESCALATE (student is stuck)
    if perf.consecutive_errors >= behavior_cfg.consecutive_wrong_for_escalate:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.ESCALATE,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=True,
            reasoning=f"Fast-track escalation: {perf.consecutive_errors} consecutive wrong answers"
        )

    # Check escalation conditions (applies to most states)
    if _should_escalate(perf, config):
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.ESCALATE,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=True,
            reasoning=f"Escalating: {perf.total_attempts} attempts, {perf.consecutive_errors} consecutive errors"
        )
    
    # State-specific transition logic
    if state == ObjectiveTeachingState.NOT_STARTED:
        return _from_not_started(config)
    
    elif state == ObjectiveTeachingState.DIAGNOSING:
        return _from_diagnosing(perf, config)
    
    elif state == ObjectiveTeachingState.EXPOSING:
        return _from_exposing(perf, config)
    
    elif state == ObjectiveTeachingState.SUPPORTING:
        return _from_supporting(perf, config)
    
    elif state == ObjectiveTeachingState.GUIDED_PRACTICE:
        return _from_guided_practice(perf, config)
    
    elif state == ObjectiveTeachingState.INDEPENDENT_PRACTICE:
        return _from_independent_practice(perf, config)
    
    elif state == ObjectiveTeachingState.CHECKING:
        return _from_checking(perf, config)
    
    elif state == ObjectiveTeachingState.CONSOLIDATING:
        return _from_consolidating(perf, config)
    
    elif state == ObjectiveTeachingState.MASTERED:
        # Terminal state - stay mastered
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.MASTERED,
            mastery_estimate=MasteryEstimate.HIGH,
            escalate_flag=False,
            reasoning="Already mastered, no transition"
        )
    
    elif state == ObjectiveTeachingState.ESCALATE:
        # Terminal state - stay escalated
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.ESCALATE,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=True,
            reasoning="Already escalated, no transition"
        )
    
    else:
        # Unknown state - should never happen
        return ObjectiveStateTransitionOutput(
            next_state=state,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=False,
            reasoning=f"Unknown state: {state}"
        )


# =============================================================================
# State Transition Helpers
# =============================================================================

def _should_escalate(perf: ObjectivePerformanceSnapshot, config: ObjectiveTeachingConfig) -> bool:
    """Check if performance warrants escalation (student is truly struggling)."""
    # Too many consecutive errors — strong signal of being stuck
    if config.max_consecutive_errors_before_escalate:
        if perf.consecutive_errors >= config.max_consecutive_errors_before_escalate:
            return True
    
    # Too many total attempts AND still performing poorly.
    # A student with high accuracy who has answered many questions should NOT
    # be escalated — they should progress toward mastery instead.
    if perf.total_attempts >= config.max_total_attempts_before_escalate:
        if perf.accuracy < config.practice_accuracy_threshold:
            return True
    
    return False


def _from_not_started(config: ObjectiveTeachingConfig) -> ObjectiveStateTransitionOutput:
    """Transition from NOT_STARTED"""
    if config.skip_diagnosing:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.EXPOSING,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=False,
            reasoning="Skipping diagnosing (config), moving to exposing"
        )
    else:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.DIAGNOSING,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=False,
            reasoning="Starting with diagnosing to probe prior knowledge"
        )


def _from_diagnosing(perf: ObjectivePerformanceSnapshot, config: ObjectiveTeachingConfig) -> ObjectiveStateTransitionOutput:
    """Transition from DIAGNOSING"""
    # Need at least 1-2 diagnostic attempts to decide
    if perf.total_attempts < 1:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.DIAGNOSING,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=False,
            reasoning="Still diagnosing - need at least 1 attempt"
        )
    
    # High accuracy on initial attempts -> can skip straight to independent practice
    if perf.accuracy >= 0.8 and perf.total_attempts >= 2:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.INDEPENDENT_PRACTICE,
            mastery_estimate=MasteryEstimate.HIGH,
            escalate_flag=False,
            reasoning=f"Strong prior knowledge ({perf.accuracy:.0%} accuracy), skipping to independent practice"
        )
    
    # Medium accuracy -> guided practice
    if perf.accuracy >= 0.5:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            mastery_estimate=MasteryEstimate.MEDIUM,
            escalate_flag=False,
            reasoning=f"Some prior knowledge ({perf.accuracy:.0%}), moving to guided practice"
        )
    
    # Low accuracy -> needs explanation
    return ObjectiveStateTransitionOutput(
        next_state=ObjectiveTeachingState.EXPOSING,
        mastery_estimate=MasteryEstimate.LOW,
        escalate_flag=False,
        reasoning=f"Weak prior knowledge ({perf.accuracy:.0%}), needs explanation"
    )


def _from_exposing(perf: ObjectivePerformanceSnapshot, config: ObjectiveTeachingConfig) -> ObjectiveStateTransitionOutput:
    """Transition from EXPOSING"""
    # After explanation and 1-2 modeled examples, move to guided practice
    # (Assuming we track "examples shown" via total_attempts in this state)
    if perf.total_attempts >= 1:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=False,
            reasoning="Explanation complete, moving to guided practice"
        )
    
    return ObjectiveStateTransitionOutput(
        next_state=ObjectiveTeachingState.EXPOSING,
        mastery_estimate=MasteryEstimate.LOW,
        escalate_flag=False,
        reasoning="Still exposing - showing examples"
    )


def _from_supporting(perf: ObjectivePerformanceSnapshot, config: ObjectiveTeachingConfig) -> ObjectiveStateTransitionOutput:
    """Transition from SUPPORTING (extra scaffolding when student is stuck)"""
    # After 1 supportive interaction, move to guided practice
    if perf.total_attempts >= 1:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=False,
            reasoning="Support provided, moving to guided practice"
        )
    
    return ObjectiveStateTransitionOutput(
        next_state=ObjectiveTeachingState.SUPPORTING,
        mastery_estimate=MasteryEstimate.LOW,
        escalate_flag=False,
        reasoning="Still supporting - providing scaffolding"
    )


def _from_guided_practice(perf: ObjectivePerformanceSnapshot, config: ObjectiveTeachingConfig) -> ObjectiveStateTransitionOutput:
    """Transition from GUIDED_PRACTICE"""
    # Need minimum practice questions
    if perf.total_attempts < config.min_practice_questions:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            mastery_estimate=_estimate_mastery(perf.accuracy),
            escalate_flag=False,
            reasoning=f"Still practicing ({perf.total_attempts}/{config.min_practice_questions} questions)"
        )
    
    # Good accuracy -> move to independent practice
    if perf.accuracy >= config.practice_accuracy_threshold:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.INDEPENDENT_PRACTICE,
            mastery_estimate=MasteryEstimate.MEDIUM,
            escalate_flag=False,
            reasoning=f"Good accuracy ({perf.accuracy:.0%}), moving to independent practice"
        )
    
    # Still struggling after many attempts -> stay in guided or escalate (handled by _should_escalate)
    return ObjectiveStateTransitionOutput(
        next_state=ObjectiveTeachingState.GUIDED_PRACTICE,
        mastery_estimate=MasteryEstimate.LOW,
        escalate_flag=False,
        reasoning=f"Below threshold ({perf.accuracy:.0%} < {config.practice_accuracy_threshold:.0%}), continuing guided practice"
    )


def _from_independent_practice(perf: ObjectivePerformanceSnapshot, config: ObjectiveTeachingConfig) -> ObjectiveStateTransitionOutput:
    """Transition from INDEPENDENT_PRACTICE"""
    # Need minimum practice questions
    if perf.total_attempts < config.min_practice_questions:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.INDEPENDENT_PRACTICE,
            mastery_estimate=_estimate_mastery(perf.accuracy),
            escalate_flag=False,
            reasoning=f"Still practicing independently ({perf.total_attempts}/{config.min_practice_questions} questions)"
        )
    
    # Good accuracy -> move to checking
    if perf.accuracy >= config.practice_accuracy_threshold:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.CHECKING,
            mastery_estimate=MasteryEstimate.MEDIUM,
            escalate_flag=False,
            reasoning=f"Good independent performance ({perf.accuracy:.0%}), moving to mastery check"
        )
    
    # Performance dropped -> back to guided practice
    if perf.accuracy < config.practice_accuracy_threshold * 0.8:  # Significant drop
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=False,
            reasoning=f"Performance drop ({perf.accuracy:.0%}), returning to guided practice"
        )
    
    # Borderline - keep practicing
    return ObjectiveStateTransitionOutput(
        next_state=ObjectiveTeachingState.INDEPENDENT_PRACTICE,
        mastery_estimate=MasteryEstimate.MEDIUM,
        escalate_flag=False,
        reasoning=f"Borderline performance ({perf.accuracy:.0%}), continuing independent practice"
    )


def _from_checking(perf: ObjectivePerformanceSnapshot, config: ObjectiveTeachingConfig) -> ObjectiveStateTransitionOutput:
    """Transition from CHECKING"""
    # Need minimum check questions
    if perf.total_attempts < config.min_check_questions:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.CHECKING,
            mastery_estimate=_estimate_mastery(perf.accuracy),
            escalate_flag=False,
            reasoning=f"Still checking mastery ({perf.total_attempts}/{config.min_check_questions} questions)"
        )
    
    # High accuracy -> mastered!
    if perf.accuracy >= config.check_accuracy_threshold:
        if config.skip_consolidating:
            return ObjectiveStateTransitionOutput(
                next_state=ObjectiveTeachingState.MASTERED,
                mastery_estimate=MasteryEstimate.HIGH,
                escalate_flag=False,
                reasoning=f"Mastery achieved ({perf.accuracy:.0%}), skipping consolidation"
            )
        else:
            return ObjectiveStateTransitionOutput(
                next_state=ObjectiveTeachingState.CONSOLIDATING,
                mastery_estimate=MasteryEstimate.HIGH,
                escalate_flag=False,
                reasoning=f"Mastery achieved ({perf.accuracy:.0%}), consolidating"
            )
    
    # Below threshold -> return to practice
    if perf.accuracy >= config.practice_accuracy_threshold:
        # Not quite mastery, but decent - go back to independent practice
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.INDEPENDENT_PRACTICE,
            mastery_estimate=MasteryEstimate.MEDIUM,
            escalate_flag=False,
            reasoning=f"Below mastery threshold ({perf.accuracy:.0%}), returning to independent practice"
        )
    else:
        # Significant gap - go back to guided practice
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            mastery_estimate=MasteryEstimate.LOW,
            escalate_flag=False,
            reasoning=f"Well below threshold ({perf.accuracy:.0%}), returning to guided practice"
        )


def _from_consolidating(perf: ObjectivePerformanceSnapshot, config: ObjectiveTeachingConfig) -> ObjectiveStateTransitionOutput:
    """Transition from CONSOLIDATING"""
    # After 1-2 consolidation interactions, move to mastered
    # (Assuming consolidation is tracked via total_attempts in this state)
    if perf.total_attempts >= 1:
        return ObjectiveStateTransitionOutput(
            next_state=ObjectiveTeachingState.MASTERED,
            mastery_estimate=MasteryEstimate.HIGH,
            escalate_flag=False,
            reasoning="Consolidation complete, objective mastered"
        )
    
    return ObjectiveStateTransitionOutput(
        next_state=ObjectiveTeachingState.CONSOLIDATING,
        mastery_estimate=MasteryEstimate.HIGH,
        escalate_flag=False,
        reasoning="Still consolidating knowledge"
    )


def _estimate_mastery(accuracy: float) -> MasteryEstimate:
    """Estimate mastery level from accuracy"""
    if accuracy >= 0.75:
        return MasteryEstimate.HIGH
    elif accuracy >= 0.5:
        return MasteryEstimate.MEDIUM
    else:
        return MasteryEstimate.LOW

