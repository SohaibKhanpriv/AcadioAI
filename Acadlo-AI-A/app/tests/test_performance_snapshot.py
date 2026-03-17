"""
Unit tests for performance_snapshot module.

Tests update_performance_snapshot with various scenarios:
- Non-answer turns
- Correct answers
- Incorrect answers
- Partially correct answers
- Rolling window behavior
"""
import pytest
from app.tutor.enums import AffectSignal
from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    TurnKind,
    AnswerCorrectness,
    ErrorCategory,
    ReasoningQuality
)
from app.tutor.types import ObjectivePerformanceSnapshot
from app.tutor.performance_snapshot import (
    update_performance_snapshot,
    build_initial_performance_snapshot
)


class TestBuildInitialPerformanceSnapshot:
    """Tests for build_initial_performance_snapshot"""
    
    def test_creates_empty_snapshot(self):
        """Initial snapshot should have all zeros and empty lists"""
        snapshot = build_initial_performance_snapshot()
        
        assert snapshot.total_attempts == 0
        assert snapshot.correct_attempts == 0
        assert snapshot.incorrect_attempts == 0
        assert snapshot.recent_answers == []
        assert snapshot.recent_affect is None


class TestUpdatePerformanceSnapshotNonAnswer:
    """Tests for non-answer turn types"""
    
    def test_question_turn_does_not_increment_counts(self):
        """Question turns should not affect attempt counts"""
        previous = build_initial_performance_snapshot()
        analysis = StudentTurnAnalysis(
            kind=TurnKind.QUESTION,
            correctness=AnswerCorrectness.NOT_APPLICABLE,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.NEUTRAL
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        assert updated.total_attempts == 0
        assert updated.correct_attempts == 0
        assert updated.incorrect_attempts == 0
        assert updated.recent_answers == []
    
    def test_meta_turn_updates_affect_only(self):
        """Meta turns should update affect but not counts"""
        previous = build_initial_performance_snapshot()
        analysis = StudentTurnAnalysis(
            kind=TurnKind.META,
            correctness=AnswerCorrectness.NOT_APPLICABLE,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.FRUSTRATED
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        assert updated.total_attempts == 0
        assert updated.recent_affect == AffectSignal.FRUSTRATED
    
    def test_small_talk_turn_does_not_increment_counts(self):
        """Small talk turns should not affect attempt counts"""
        previous = ObjectivePerformanceSnapshot(
            total_attempts=5,
            correct_attempts=3,
            incorrect_attempts=2,
            recent_answers=[{"correct": True}],
            recent_affect=None
        )
        analysis = StudentTurnAnalysis(
            kind=TurnKind.SMALL_TALK,
            correctness=AnswerCorrectness.NOT_APPLICABLE,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.BORED
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        # Counts should remain unchanged
        assert updated.total_attempts == 5
        assert updated.correct_attempts == 3
        assert updated.incorrect_attempts == 2
        # But affect should update
        assert updated.recent_affect == AffectSignal.BORED


class TestUpdatePerformanceSnapshotCorrectAnswer:
    """Tests for correct answer handling"""
    
    def test_correct_answer_increments_counts(self):
        """Correct answer should increment total and correct counts"""
        previous = build_initial_performance_snapshot()
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.CORRECT,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.CONFIDENT
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        assert updated.total_attempts == 1
        assert updated.correct_attempts == 1
        assert updated.incorrect_attempts == 0
    
    def test_correct_answer_adds_to_recent(self):
        """Correct answer should add record to recent_answers"""
        previous = build_initial_performance_snapshot()
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.CORRECT,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.NEUTRAL
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        assert len(updated.recent_answers) == 1
        assert updated.recent_answers[0]["correct"] is True
        assert updated.recent_answers[0]["correctness"] == "correct"
        assert updated.recent_answers[0]["error_category"] == "none"


class TestUpdatePerformanceSnapshotIncorrectAnswer:
    """Tests for incorrect and partially correct answer handling"""
    
    def test_incorrect_answer_increments_counts(self):
        """Incorrect answer should increment total and incorrect counts"""
        previous = build_initial_performance_snapshot()
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.CONCEPTUAL,
            affect=AffectSignal.ANXIOUS
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        assert updated.total_attempts == 1
        assert updated.correct_attempts == 0
        assert updated.incorrect_attempts == 1
    
    def test_partially_correct_counts_as_incorrect(self):
        """Partially correct answer should increment incorrect count (v1 behavior)"""
        previous = build_initial_performance_snapshot()
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.PARTIALLY_CORRECT,
            error_category=ErrorCategory.PROCEDURE,
            affect=AffectSignal.NEUTRAL
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        assert updated.total_attempts == 1
        assert updated.correct_attempts == 0
        assert updated.incorrect_attempts == 1
    
    def test_incorrect_answer_records_error_category(self):
        """Incorrect answer should record error category in recent_answers"""
        previous = build_initial_performance_snapshot()
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.CARELESS,
            affect=AffectSignal.FRUSTRATED
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        assert len(updated.recent_answers) == 1
        assert updated.recent_answers[0]["correct"] is False
        assert updated.recent_answers[0]["error_category"] == "careless"

    def test_non_attempt_not_applicable_does_not_increment(self):
        """Non-attempt responses should not count as incorrect attempts."""
        previous = build_initial_performance_snapshot()
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.NOT_APPLICABLE,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.ANXIOUS
        )

        updated = update_performance_snapshot(previous, analysis)

        assert updated.total_attempts == 0
        assert updated.correct_attempts == 0
        assert updated.incorrect_attempts == 0
        assert len(updated.recent_answers) == 0


class TestUpdatePerformanceSnapshotRollingWindow:
    """Tests for rolling window behavior"""
    
    def test_rolling_window_trims_to_max(self):
        """Recent answers should be trimmed to max_recent"""
        # Start with 9 answers
        previous = ObjectivePerformanceSnapshot(
            total_attempts=9,
            correct_attempts=5,
            incorrect_attempts=4,
            recent_answers=[{"correct": True} for _ in range(9)],
            recent_affect=None
        )
        
        # Add 2 more with max_recent=10
        analysis1 = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.CORRECT,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.NEUTRAL
        )
        
        updated1 = update_performance_snapshot(previous, analysis1, max_recent=10)
        assert len(updated1.recent_answers) == 10
        
        analysis2 = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.CONCEPTUAL,
            affect=AffectSignal.FRUSTRATED
        )
        
        updated2 = update_performance_snapshot(updated1, analysis2, max_recent=10)
        assert len(updated2.recent_answers) == 10
        # Most recent should be incorrect
        assert updated2.recent_answers[-1]["correct"] is False
    
    def test_rolling_window_keeps_most_recent(self):
        """Rolling window should keep the most recent answers"""
        previous = ObjectivePerformanceSnapshot(
            total_attempts=5,
            correct_attempts=5,
            incorrect_attempts=0,
            recent_answers=[{"correct": True, "index": i} for i in range(5)],
            recent_affect=None
        )
        
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.PROCEDURE,
            affect=AffectSignal.NEUTRAL
        )
        
        updated = update_performance_snapshot(previous, analysis, max_recent=3)
        
        # Should have last 2 from previous + new one
        assert len(updated.recent_answers) == 3
        assert updated.recent_answers[-1]["correct"] is False


class TestUpdatePerformanceSnapshotAffect:
    """Tests for affect signal handling"""
    
    def test_affect_is_always_updated(self):
        """Affect should be updated regardless of turn kind"""
        previous = ObjectivePerformanceSnapshot(
            total_attempts=0,
            correct_attempts=0,
            incorrect_attempts=0,
            recent_answers=[],
            recent_affect=AffectSignal.NEUTRAL
        )
        
        analysis = StudentTurnAnalysis(
            kind=TurnKind.OFF_TOPIC,
            correctness=AnswerCorrectness.NOT_APPLICABLE,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.BORED
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        assert updated.recent_affect == AffectSignal.BORED
    
    def test_affect_is_enum_type(self):
        """recent_affect should be AffectSignal enum type"""
        previous = build_initial_performance_snapshot()
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.CORRECT,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.CONFIDENT
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        assert isinstance(updated.recent_affect, AffectSignal)
        assert updated.recent_affect == AffectSignal.CONFIDENT


class TestUpdatePerformanceSnapshotImmutability:
    """Tests for immutability behavior"""
    
    def test_does_not_mutate_previous_snapshot(self):
        """update_performance_snapshot should not mutate the previous snapshot"""
        previous = ObjectivePerformanceSnapshot(
            total_attempts=5,
            correct_attempts=3,
            incorrect_attempts=2,
            recent_answers=[{"correct": True}],
            recent_affect=AffectSignal.NEUTRAL
        )
        
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.CORRECT,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.CONFIDENT
        )
        
        updated = update_performance_snapshot(previous, analysis)
        
        # Previous should be unchanged
        assert previous.total_attempts == 5
        assert previous.correct_attempts == 3
        assert len(previous.recent_answers) == 1
        assert previous.recent_affect == AffectSignal.NEUTRAL
        
        # Updated should be different
        assert updated.total_attempts == 6
        assert updated.correct_attempts == 4
        assert len(updated.recent_answers) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

