"""
Performance snapshot update logic.

This module provides pure functions for updating ObjectivePerformanceSnapshot
from StudentTurnAnalysis results.
"""
from copy import deepcopy
from typing import Dict, Any

from app.tutor.enums import AffectSignal
from app.tutor.types import ObjectivePerformanceSnapshot
from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    TurnKind,
    AnswerCorrectness,
)


def update_performance_snapshot(
    previous: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    max_recent: int = 10,
) -> ObjectivePerformanceSnapshot:
    """
    Given the previous performance snapshot and the latest StudentTurnAnalysis,
    return an updated ObjectivePerformanceSnapshot.
    
    This is a pure function with no side effects.
    
    Args:
        previous: The previous performance snapshot
        analysis: The latest student turn analysis
        max_recent: Maximum number of recent answers to keep (default 10)
        
    Returns:
        Updated ObjectivePerformanceSnapshot
        
    Behavior:
        - Only updates counts when the turn is ANSWER
        - Maintains a rolling window of recent answers (length <= max_recent)
        - Updates recent_affect from analysis.affect (as AffectSignal enum)
    """
    # Create a new snapshot (don't mutate the input)
    new_snapshot = ObjectivePerformanceSnapshot(
        total_attempts=previous.total_attempts,
        correct_attempts=previous.correct_attempts,
        incorrect_attempts=previous.incorrect_attempts,
        recent_answers=deepcopy(previous.recent_answers),
        recent_affect=analysis.affect  # AffectSignal enum
    )
    
    # Only update counts for ANSWER turns with gradable correctness.
    # Non-attempt responses (e.g., "I don't know") should be represented as
    # correctness=NOT_APPLICABLE and must not count as incorrect attempts.
    if analysis.kind == TurnKind.ANSWER:
        if analysis.correctness in [
            AnswerCorrectness.CORRECT,
            AnswerCorrectness.PARTIALLY_CORRECT,
            AnswerCorrectness.INCORRECT,
        ]:
            # Increment total attempts
            new_snapshot.total_attempts += 1

            # Update correct/incorrect counts based on correctness
            if analysis.correctness == AnswerCorrectness.CORRECT:
                new_snapshot.correct_attempts += 1
            else:
                # For v1, treat partially_correct as "not fully correct"
                new_snapshot.incorrect_attempts += 1

            # Add new answer record to recent_answers
            answer_record: Dict[str, Any] = {
                "correct": analysis.correctness == AnswerCorrectness.CORRECT,
                "correctness": analysis.correctness.value,
                "error_category": analysis.error_category.value,
            }

            new_snapshot.recent_answers.append(answer_record)

            # Trim to max_recent (keep the most recent)
            if len(new_snapshot.recent_answers) > max_recent:
                new_snapshot.recent_answers = new_snapshot.recent_answers[-max_recent:]
    
    return new_snapshot


def build_initial_performance_snapshot() -> ObjectivePerformanceSnapshot:
    """
    Create an initial (empty) ObjectivePerformanceSnapshot.
    
    Returns:
        Fresh ObjectivePerformanceSnapshot with all counts at zero
    """
    return ObjectivePerformanceSnapshot(
        total_attempts=0,
        correct_attempts=0,
        incorrect_attempts=0,
        recent_answers=[],
        recent_affect=None
    )

