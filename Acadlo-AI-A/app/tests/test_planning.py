"""
Unit tests for Tutor Planning (M4-E).

Tests plan_next_tutor_action with various scenarios as required:
- High mastery in GUIDED_PRACTICE
- Low performance with conceptual errors
- High stability in INDEPENDENT_PRACTICE
- Persistent failure and negative affect
- MASTERED and ESCALATE states
"""
import pytest
from app.tutor.enums import ObjectiveTeachingState, AffectSignal
from app.tutor.types import ObjectivePerformanceSnapshot, ObjectiveTeachingConfig
from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    TurnKind,
    AnswerCorrectness,
    ErrorCategory,
)
from app.tutor.action_schema import (
    TutorActionKind,
    TutorActionPlan,
    DifficultyAdjustment,
)
from app.tutor.planning import plan_next_tutor_action, _should_encourage


# ============================================================================
# Test Fixtures / Helpers
# ============================================================================

def make_snapshot(
    total: int = 0,
    correct: int = 0,
    incorrect: int = 0,
    recent_answers: list = None,
    affect: AffectSignal = None,
) -> ObjectivePerformanceSnapshot:
    """Helper to create performance snapshots for tests."""
    return ObjectivePerformanceSnapshot(
        total_attempts=total,
        correct_attempts=correct,
        incorrect_attempts=incorrect,
        recent_answers=recent_answers or [],
        recent_affect=affect,
    )


def make_analysis(
    kind: TurnKind = TurnKind.ANSWER,
    correctness: AnswerCorrectness = AnswerCorrectness.CORRECT,
    error_category: ErrorCategory = ErrorCategory.NONE,
    affect: AffectSignal = AffectSignal.NEUTRAL,
) -> StudentTurnAnalysis:
    """Helper to create student turn analysis for tests."""
    return StudentTurnAnalysis(
        kind=kind,
        correctness=correctness,
        error_category=error_category,
        affect=affect,
    )


def make_config(
    objective_id: str = "test-obj",
    min_practice: int = 3,
    practice_threshold: float = 0.7,
    min_check: int = 2,
    check_threshold: float = 0.8,
    max_attempts: int = 12,
    max_errors: int = 4,
) -> ObjectiveTeachingConfig:
    """Helper to create objective config for tests."""
    return ObjectiveTeachingConfig(
        objective_id=objective_id,
        min_practice_questions=min_practice,
        practice_accuracy_threshold=practice_threshold,
        min_check_questions=min_check,
        check_accuracy_threshold=check_threshold,
        max_total_attempts_before_escalate=max_attempts,
        max_consecutive_errors_before_escalate=max_errors,
    )


# ============================================================================
# AC Tests: High mastery in GUIDED_PRACTICE
# ============================================================================

class TestGuidedPracticeHighMastery:
    """
    Given teaching_state = GUIDED_PRACTICE,
    high recent accuracy, enough attempts,
    and neutral/positive affect:
    Plan should lean toward CHECK_UNDERSTANDING or ASK_QUESTION
    with an intent that moves towards INDEPENDENT_PRACTICE.
    """
    
    def test_high_accuracy_enough_attempts_transitions_to_check(self):
        """High accuracy + enough attempts should transition to CHECK_UNDERSTANDING."""
        snapshot = make_snapshot(
            total=5,
            correct=4,
            incorrect=1,
            recent_answers=[
                {"correct": True},
                {"correct": True},
                {"correct": True},
                {"correct": True},
                {"correct": False},
            ],
        )
        analysis = make_analysis(
            correctness=AnswerCorrectness.CORRECT,
            affect=AffectSignal.CONFIDENT,
        )
        config = make_config(min_practice=3, practice_threshold=0.7)
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.CHECK_UNDERSTANDING
        assert plan.intent_label == "transition_to_independent"
    
    def test_high_accuracy_not_enough_attempts_continues_practice(self):
        """High accuracy but not enough attempts should continue practice."""
        snapshot = make_snapshot(
            total=2,
            correct=2,
            incorrect=0,
            recent_answers=[{"correct": True}, {"correct": True}],
        )
        analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        config = make_config(min_practice=3)
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.ASK_QUESTION
        assert plan.intent_label == "guided_practice_question"
        # High accuracy should suggest harder
        assert plan.difficulty_adjustment == DifficultyAdjustment.HARDER


# ============================================================================
# AC Tests: Low performance with conceptual errors
# ============================================================================

class TestGuidedPracticeLowPerformance:
    """
    Given teaching_state = GUIDED_PRACTICE,
    low accuracy, conceptual error_category,
    possibly FRUSTRATED affect:
    Plan should be EXPLAIN_CONCEPT or BREAKDOWN_STEP
    (not just ask another question).
    """
    
    def test_conceptual_error_gets_breakdown(self):
        """Conceptual error should trigger BREAKDOWN_STEP."""
        snapshot = make_snapshot(
            total=3,
            correct=0,
            incorrect=3,
            recent_answers=[
                {"correct": False, "error_category": "conceptual"},
                {"correct": False, "error_category": "conceptual"},
                {"correct": False, "error_category": "conceptual"},
            ],
        )
        analysis = make_analysis(
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.CONCEPTUAL,
            affect=AffectSignal.FRUSTRATED,
        )
        config = make_config()
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.BREAKDOWN_STEP
        assert plan.intent_label == "address_misconception"
        # Should include encouragement due to frustration
        assert plan.include_encouragement is True
    
    def test_procedural_error_gets_hint(self):
        """Procedural error should trigger GIVE_HINT."""
        snapshot = make_snapshot(
            total=2,
            correct=1,
            incorrect=1,
            recent_answers=[{"correct": True}, {"correct": False}],
        )
        analysis = make_analysis(
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.PROCEDURE,
        )
        config = make_config()
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.GIVE_HINT
        assert plan.intent_label == "scaffold_step"


# ============================================================================
# AC Tests: High stability in INDEPENDENT_PRACTICE
# ============================================================================

class TestIndependentPracticeHighStability:
    """
    Given teaching_state = INDEPENDENT_PRACTICE,
    high accuracy and enough attempts:
    Plan should be CHECK_UNDERSTANDING or a "mastery check" type action.
    """
    
    def test_high_accuracy_triggers_mastery_check(self):
        """High accuracy in independent practice should check mastery."""
        snapshot = make_snapshot(
            total=5,
            correct=5,
            incorrect=0,
            recent_answers=[{"correct": True}] * 5,
        )
        analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        config = make_config(practice_threshold=0.7)
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.INDEPENDENT_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.CHECK_UNDERSTANDING
        assert plan.intent_label == "check_mastery"
    
    def test_moderate_accuracy_continues_practice(self):
        """Moderate accuracy should continue independent practice."""
        snapshot = make_snapshot(
            total=4,
            correct=2,
            incorrect=2,
            recent_answers=[
                {"correct": True},
                {"correct": False},
                {"correct": True},
                {"correct": False},
            ],
        )
        analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        config = make_config(practice_threshold=0.7)
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.INDEPENDENT_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.ASK_QUESTION
        assert plan.intent_label == "independent_practice_question"


# ============================================================================
# AC Tests: Persistent failure and negative affect
# ============================================================================

class TestPersistentFailureAndNegativeAffect:
    """
    When performance is poor for many attempts (consistent with escalation triggers)
    and/or affect is repeatedly negative:
    Plan should move to ESCALATE or at least propose a "simplify and encourage" action.
    """
    
    def test_frustrated_with_errors_gets_explanation_and_encouragement(self):
        """Frustrated student with errors gets explanation + encouragement."""
        snapshot = make_snapshot(
            total=5,
            correct=1,
            incorrect=4,
            recent_answers=[
                {"correct": False},
                {"correct": False},
                {"correct": True},
                {"correct": False},
                {"correct": False},
            ],
        )
        analysis = make_analysis(
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.CONCEPTUAL,
            affect=AffectSignal.FRUSTRATED,
        )
        config = make_config()
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.INDEPENDENT_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.EXPLAIN_CONCEPT
        assert plan.include_encouragement is True
        assert plan.difficulty_adjustment == DifficultyAdjustment.EASIER
    
    def test_consecutive_errors_triggers_support(self):
        """Multiple consecutive errors should trigger support."""
        snapshot = make_snapshot(
            total=4,
            correct=1,
            incorrect=3,
            recent_answers=[
                {"correct": True},
                {"correct": False},
                {"correct": False},
                {"correct": False},
            ],
        )
        analysis = make_analysis(
            correctness=AnswerCorrectness.INCORRECT,
            affect=AffectSignal.ANXIOUS,
        )
        config = make_config()
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.INDEPENDENT_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        # Should get support with encouragement
        assert plan.include_encouragement is True
        assert plan.kind in [
            TutorActionKind.EXPLAIN_CONCEPT,
            TutorActionKind.GIVE_HINT,
        ]


# ============================================================================
# AC Tests: MASTERED and ESCALATE states
# ============================================================================

class TestMasteredState:
    """For MASTERED, plan usually suggests SWITCH_OBJECTIVE or END_LESSON."""
    
    def test_mastered_suggests_switch_objective(self):
        """MASTERED state should suggest switching to next objective."""
        snapshot = make_snapshot(total=5, correct=5, incorrect=0)
        analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        config = make_config(objective_id="math-obj-1")
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.MASTERED,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.SWITCH_OBJECTIVE
        assert plan.intent_label == "objective_mastered_move_next"
        assert plan.metadata.get("mastered_objective") == "math-obj-1"


class TestEscalateState:
    """For ESCALATE, plan should be ESCALATE with clear metadata (reason)."""
    
    def test_escalate_includes_reason_too_many_attempts(self):
        """ESCALATE state should include reason for escalation."""
        snapshot = make_snapshot(
            total=15,
            correct=3,
            incorrect=12,
            recent_answers=[{"correct": False}] * 5,
        )
        analysis = make_analysis(
            correctness=AnswerCorrectness.INCORRECT,
            affect=AffectSignal.FRUSTRATED,
        )
        config = make_config(max_attempts=12, max_errors=4)
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.ESCALATE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.ESCALATE
        assert plan.escalation_reason is not None
        assert "too_many_attempts" in plan.escalation_reason
        assert plan.metadata.get("total_attempts") == 15
    
    def test_escalate_includes_reason_persistent_errors(self):
        """ESCALATE should note persistent errors."""
        snapshot = make_snapshot(
            total=8,
            correct=2,
            incorrect=6,
            recent_answers=[{"correct": False}] * 5,
        )
        analysis = make_analysis(correctness=AnswerCorrectness.INCORRECT)
        config = make_config(max_attempts=12, max_errors=4)
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.ESCALATE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.ESCALATE
        assert "persistent_errors" in plan.escalation_reason


# ============================================================================
# Additional Tests: Determinism and Sensibility
# ============================================================================

class TestPlanningDeterminism:
    """Tests confirm the function is deterministic given the same inputs."""
    
    def test_same_inputs_same_output(self):
        """Same inputs should produce identical outputs."""
        snapshot = make_snapshot(total=3, correct=2, incorrect=1)
        analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        config = make_config()
        
        plan1 = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        plan2 = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan1.kind == plan2.kind
        assert plan1.intent_label == plan2.intent_label
        assert plan1.difficulty_adjustment == plan2.difficulty_adjustment


class TestPlanningStateTransitions:
    """Small changes in performance/state cause sensible changes in actions."""
    
    def test_improving_accuracy_changes_difficulty(self):
        """Improving accuracy should increase difficulty suggestion."""
        config = make_config(min_practice=5)
        
        # Low accuracy
        low_snapshot = make_snapshot(
            total=3,
            correct=1,
            incorrect=2,
            recent_answers=[{"correct": False}, {"correct": False}, {"correct": True}],
        )
        low_plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            performance=low_snapshot,
            analysis=make_analysis(correctness=AnswerCorrectness.CORRECT),
            config=config,
        )
        
        # High accuracy
        high_snapshot = make_snapshot(
            total=4,
            correct=4,
            incorrect=0,
            recent_answers=[{"correct": True}] * 4,
        )
        high_plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.GUIDED_PRACTICE,
            performance=high_snapshot,
            analysis=make_analysis(correctness=AnswerCorrectness.CORRECT),
            config=config,
        )
        
        # High accuracy should suggest harder questions
        assert high_plan.difficulty_adjustment == DifficultyAdjustment.HARDER
        # Low accuracy should stay same
        assert low_plan.difficulty_adjustment == DifficultyAdjustment.SAME


# ============================================================================
# Tests: Encouragement Logic
# ============================================================================

class TestEncouragementLogic:
    """Tests for _should_encourage helper."""
    
    def test_frustrated_needs_encouragement(self):
        """Frustrated student should get encouragement."""
        analysis = make_analysis(affect=AffectSignal.FRUSTRATED)
        snapshot = make_snapshot()
        
        assert _should_encourage(analysis, snapshot) is True
    
    def test_anxious_needs_encouragement(self):
        """Anxious student should get encouragement."""
        analysis = make_analysis(affect=AffectSignal.ANXIOUS)
        snapshot = make_snapshot()
        
        assert _should_encourage(analysis, snapshot) is True
    
    def test_consecutive_errors_need_encouragement(self):
        """Multiple consecutive errors should trigger encouragement."""
        analysis = make_analysis(affect=AffectSignal.NEUTRAL)
        snapshot = make_snapshot(
            total=4,
            correct=2,
            incorrect=2,
            recent_answers=[
                {"correct": True},
                {"correct": True},
                {"correct": False},
                {"correct": False},
            ],
        )
        
        assert _should_encourage(analysis, snapshot) is True
    
    def test_confident_student_no_extra_encouragement(self):
        """Confident student doing well doesn't need extra encouragement."""
        analysis = make_analysis(
            correctness=AnswerCorrectness.CORRECT,
            affect=AffectSignal.CONFIDENT,
        )
        snapshot = make_snapshot(
            total=5,
            correct=5,
            incorrect=0,
            recent_answers=[{"correct": True}] * 5,
        )
        
        assert _should_encourage(analysis, snapshot) is False


# ============================================================================
# Tests: Other Teaching States
# ============================================================================

class TestDiagnosingState:
    """Tests for DIAGNOSING state planning."""
    
    def test_not_answer_asks_diagnostic_question(self):
        """Student question during diagnosis should get an explanation."""
        snapshot = make_snapshot()
        analysis = make_analysis(kind=TurnKind.QUESTION)
        config = make_config()
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.DIAGNOSING,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.EXPLAIN_CONCEPT
        assert plan.intent_label == "answer_student_question_during_diagnosis"
    
    def test_correct_answers_increase_difficulty(self):
        """Correct diagnostic answers should increase difficulty."""
        snapshot = make_snapshot(
            total=2,
            correct=2,
            incorrect=0,
            recent_answers=[{"correct": True}, {"correct": True}],
        )
        analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        config = make_config()
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.DIAGNOSING,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.difficulty_adjustment == DifficultyAdjustment.HARDER


class TestExposingState:
    """Tests for EXPOSING state planning."""
    
    def test_incorrect_conceptual_explains(self):
        """Conceptual error in exposing should explain more."""
        snapshot = make_snapshot(total=1, correct=0, incorrect=1)
        analysis = make_analysis(
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.CONCEPTUAL,
        )
        config = make_config()
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.EXPOSING,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.EXPLAIN_CONCEPT
        assert plan.intent_label == "clarify_misconception"
    
    def test_correct_moves_to_practice(self):
        """Correct answer in exposing should move to practice."""
        snapshot = make_snapshot(total=1, correct=1, incorrect=0)
        analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        config = make_config()
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.EXPOSING,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.ASK_QUESTION
        assert plan.intent_label == "guided_practice_question"


class TestCheckingState:
    """Tests for CHECKING state planning."""
    
    def test_enough_checks_with_high_accuracy_consolidates(self):
        """Enough successful checks should move to consolidation."""
        snapshot = make_snapshot(
            total=2,
            correct=2,
            incorrect=0,
            recent_answers=[{"correct": True}, {"correct": True}],
        )
        analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        config = make_config(min_check=2, check_threshold=0.8)
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.CHECKING,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.EXPLAIN_CONCEPT
        assert plan.intent_label == "summary_and_consolidation"


class TestConsolidatingState:
    """Tests for CONSOLIDATING state planning."""
    
    def test_consolidating_provides_summary(self):
        """Consolidating should provide summary."""
        snapshot = make_snapshot(total=5, correct=5, incorrect=0)
        analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        config = make_config()
        
        plan = plan_next_tutor_action(
            teaching_state=ObjectiveTeachingState.CONSOLIDATING,
            performance=snapshot,
            analysis=analysis,
            config=config,
        )
        
        assert plan.kind == TutorActionKind.META_COACHING
        assert plan.intent_label == "summary_and_links"


class TestTutorActionPlanSerialization:
    """Tests for TutorActionPlan serialization."""
    
    def test_to_dict_serializes_correctly(self):
        """TutorActionPlan.to_dict() should produce valid JSON-serializable dict."""
        plan = TutorActionPlan(
            kind=TutorActionKind.ASK_QUESTION,
            target_objective_id="obj-123",
            difficulty_adjustment=DifficultyAdjustment.HARDER,
            intent_label="guided_practice_question",
            include_encouragement=True,
            metadata={"foo": "bar"},
        )
        
        d = plan.to_dict()
        
        assert d["kind"] == "ask_question"
        assert d["target_objective_id"] == "obj-123"
        assert d["difficulty_adjustment"] == "harder"
        assert d["intent_label"] == "guided_practice_question"
        assert d["include_encouragement"] is True
        assert d["metadata"] == {"foo": "bar"}
    
    def test_to_dict_omits_none_values(self):
        """to_dict should handle None values gracefully."""
        plan = TutorActionPlan(
            kind=TutorActionKind.ENCOURAGE,
            intent_label="normalize_struggle",
        )
        
        d = plan.to_dict()
        
        assert d["kind"] == "encourage"
        assert d["target_objective_id"] is None
        assert "difficulty_adjustment" not in d  # None values omitted
        assert "escalation_reason" not in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

