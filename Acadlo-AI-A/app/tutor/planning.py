"""
Tutor Planning - Rule-Based Action Selection.

This module implements the core planning logic that decides what the tutor
should do next given the current teaching state, performance, and student analysis.

The planning function is:
- Pure (no side effects, deterministic given same inputs)
- Rule-based (explicit pedagogical rules, not LLM-based)
- Testable (easy to unit test with various scenarios)
"""
from app.tutor.enums import ObjectiveTeachingState, AffectSignal
from app.tutor.types import (
    ObjectivePerformanceSnapshot,
    ObjectiveTeachingConfig,
    DEFAULT_TUTOR_BEHAVIOR_CONFIG,
)
from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    StudentBehavior,
    TurnKind,
    AnswerCorrectness,
    ErrorCategory,
    RequestType,
)
from app.tutor.action_schema import (
    TutorActionPlan,
    TutorActionKind,
    DifficultyAdjustment,
)
from app.tutor.progress_evaluator import (
    ProgressEvaluation,
    ProgressSignal,
    RecommendedApproach,
)
from typing import Optional


def plan_next_tutor_action(
    *,
    teaching_state: ObjectiveTeachingState,
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
    no_answer_streak: int = 0,
    low_confidence: bool = False,
    progress_evaluation: Optional[ProgressEvaluation] = None,
    mcq_mode: bool = False,
) -> TutorActionPlan:
    """
    Decide what the tutor should do next.
    
    This is a pure, rule-based function that examines:
    - Current objective teaching state (from state machine)
    - Performance snapshot (attempts, accuracy, recent answers)
    - Last student turn analysis (kind, correctness, error, affect)
    - Objective config (thresholds, flags)
    - Progress evaluation (advancing/stalled/regressing + recommended approach)
    
    Returns a TutorActionPlan that will later be turned into actual messages
    by the response generation layer.
    """
    cfg = DEFAULT_TUTOR_BEHAVIOR_CONFIG
    # First check for affect-based interventions
    needs_encouragement = _should_encourage(analysis, performance)
    
    # ===== PRIORITY 1: Handle REQUEST turns immediately =====
    # When student says "explain this", "show me an example", etc.
    # Act immediately — no looping, no asking preferences.
    if analysis.kind == TurnKind.REQUEST:
        plan = _handle_request(analysis, performance)
        if needs_encouragement:
            plan.include_encouragement = True
        return plan
    
    # ===== PRIORITY 1.5: Handle OFF_TOPIC and SMALL_TALK — redirect to lesson =====
    if analysis.kind in [TurnKind.OFF_TOPIC, TurnKind.SMALL_TALK]:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="redirect_off_topic",
            metadata={"reason": f"{analysis.kind.value}_student_message"},
        )
    
    # ===== PRIORITY 1.6: Handle student QUESTION — answer directly =====
    if analysis.kind == TurnKind.QUESTION:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="answer_student_question",
            metadata={"reason": "student_asked_question"},
        )

    # ===== PRIORITY 1.7: MCQ mode — stay in MCQ or exit on correct =====
    if mcq_mode and analysis.kind == TurnKind.ANSWER:
        if analysis.correctness == AnswerCorrectness.CORRECT:
            return TutorActionPlan(
                kind=TutorActionKind.ASK_QUESTION,
                intent_label="reinforce_exit_mcq",
                metadata={"exit_mcq": True, "reason": "correct_mcq_answer"},
            )
        return TutorActionPlan(
            kind=TutorActionKind.ASK_MCQ,
            intent_label="mcq_retry",
            metadata={"reason": "wrong_mcq_answer"},
        )

    # ===== PRIORITY 1.8: Guessing detected — switch to MCQ =====
    if (
        cfg.mcq_trigger_on_guessing
        and not mcq_mode
        and analysis.kind == TurnKind.ANSWER
        and (analysis.likely_guessing or analysis.behavior == StudentBehavior.GUESSING)
    ):
        return TutorActionPlan(
            kind=TutorActionKind.ASK_MCQ,
            intent_label="switch_to_mcq",
            metadata={"set_mcq_mode": True, "reason": "student_guessing"},
        )

    # ===== PRIORITY 2: Handle stuck/low-confidence with AI auto-decision =====
    if low_confidence or no_answer_streak >= 2:
        if teaching_state in [
            ObjectiveTeachingState.DIAGNOSING,
            ObjectiveTeachingState.SUPPORTING,
            ObjectiveTeachingState.GUIDED_PRACTICE,
            ObjectiveTeachingState.INDEPENDENT_PRACTICE,
            ObjectiveTeachingState.EXPOSING,
        ]:
            plan = _auto_decide_support(
                analysis=analysis,
                performance=performance,
                progress_evaluation=progress_evaluation,
                no_answer_streak=no_answer_streak,
            )
            if _should_encourage(analysis, performance):
                plan.include_encouragement = True
            return plan

    # ===== PRIORITY 2.5: Two consecutive wrong answers — simplify and change method =====
    if (
        not mcq_mode
        and analysis.kind == TurnKind.ANSWER
        and analysis.correctness == AnswerCorrectness.INCORRECT
        and performance.consecutive_errors >= cfg.wrong_streak_simplify_threshold
    ):
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="simplify_and_change_method",
            difficulty_adjustment=DifficultyAdjustment.EASIER,
            include_encouragement=needs_encouragement,
            metadata={"reason": "two_consecutive_wrong"},
        )

    # ===== PRIORITY 2.6: Correct answer and advancing — brief reinforcement then harder =====
    if (
        analysis.kind == TurnKind.ANSWER
        and analysis.correctness == AnswerCorrectness.CORRECT
        and progress_evaluation
        and progress_evaluation.signal == ProgressSignal.ADVANCING
    ):
        return TutorActionPlan(
            kind=TutorActionKind.ASK_QUESTION,
            intent_label="reinforce_briefly_then_harder",
            difficulty_adjustment=DifficultyAdjustment.HARDER,
            metadata={"reason": "correct_advancing"},
        )

    # ===== PRIORITY 3: Use progress evaluation to adapt =====
    if progress_evaluation and progress_evaluation.signal != ProgressSignal.ADVANCING:
        plan = _adapt_for_progress(
            progress_evaluation=progress_evaluation,
            teaching_state=teaching_state,
            analysis=analysis,
            performance=performance,
            config=config,
        )
        if plan:
            if needs_encouragement:
                plan.include_encouragement = True
            return plan

    # ===== PRIORITY 4: Route to state-specific planning =====
    if teaching_state == ObjectiveTeachingState.NOT_STARTED:
        plan = _plan_for_not_started(performance, analysis, config)
    
    elif teaching_state == ObjectiveTeachingState.DIAGNOSING:
        plan = _plan_for_diagnosing(performance, analysis, config)
    
    elif teaching_state == ObjectiveTeachingState.EXPOSING:
        plan = _plan_for_exposing(performance, analysis, config)

    elif teaching_state == ObjectiveTeachingState.SUPPORTING:
        plan = _plan_for_supporting(performance, analysis, config)
    
    elif teaching_state == ObjectiveTeachingState.GUIDED_PRACTICE:
        plan = _plan_for_guided_practice(performance, analysis, config)
    
    elif teaching_state == ObjectiveTeachingState.INDEPENDENT_PRACTICE:
        plan = _plan_for_independent_practice(performance, analysis, config)
    
    elif teaching_state == ObjectiveTeachingState.CHECKING:
        plan = _plan_for_checking(performance, analysis, config)
    
    elif teaching_state == ObjectiveTeachingState.CONSOLIDATING:
        plan = _plan_for_consolidating(performance, analysis, config)
    
    elif teaching_state == ObjectiveTeachingState.MASTERED:
        plan = _plan_for_mastered(performance, analysis, config)
    
    elif teaching_state == ObjectiveTeachingState.ESCALATE:
        plan = _plan_for_escalate(performance, analysis, config)
    
    else:
        plan = TutorActionPlan(
            kind=TutorActionKind.ASK_QUESTION,
            intent_label="fallback_question",
        )
    
    if needs_encouragement:
        plan.include_encouragement = True
    
    return plan


# =============================================================================
# REQUEST Handling (fixes the question-loop bug)
# =============================================================================

def _handle_request(
    analysis: StudentTurnAnalysis,
    performance: ObjectivePerformanceSnapshot,
) -> TutorActionPlan:
    """
    Handle REQUEST turns — student is asking for a specific kind of help.
    Act immediately without asking "how would you like help?"
    """
    request_type = analysis.request_type or RequestType.UNKNOWN
    
    if request_type == RequestType.EXPLAIN:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="direct_explain_on_request",
            metadata={"triggered_by": "student_request", "request_type": "explain"},
        )
    
    elif request_type == RequestType.EXAMPLE:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="direct_example_on_request",
            metadata={"triggered_by": "student_request", "request_type": "example"},
        )
    
    elif request_type == RequestType.STEP_BY_STEP:
        return TutorActionPlan(
            kind=TutorActionKind.BREAKDOWN_STEP,
            intent_label="direct_breakdown_on_request",
            metadata={"triggered_by": "student_request", "request_type": "step_by_step"},
        )
    
    elif request_type == RequestType.REPEAT:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="repeat_last_explanation",
            metadata={"triggered_by": "student_request", "request_type": "repeat"},
        )
    
    else:
        # Unknown request — default to explanation
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="direct_explain_on_request",
            metadata={"triggered_by": "student_request", "request_type": "unknown"},
        )


# =============================================================================
# Auto-Decide Support (replaces "ask what help they want" loop)
# =============================================================================

def _auto_decide_support(
    *,
    analysis: StudentTurnAnalysis,
    performance: ObjectivePerformanceSnapshot,
    progress_evaluation: Optional[ProgressEvaluation],
    no_answer_streak: int,
) -> TutorActionPlan:
    """
    AI auto-decides what kind of support to provide when student is stuck.
    
    ESCALATION LEVELS based on how stuck the student is:
    - Streak 2: micro-step with gentle check
    - Streak 3: empathy first, then teach (no quiz)
    - Streak 4+: pure teaching mode (zero questions, just explain)
    
    Within each level, uses error category and affect to pick the approach.
    """
    # ===== ESCALATION: More stuck = less quizzing =====
    
    if no_answer_streak >= 4:
        # Student is completely lost. STOP ALL QUIZZING.
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="pure_teach_no_quiz",
            difficulty_adjustment=DifficultyAdjustment.EASIER,
            include_encouragement=True,
            metadata={
                "auto_support": True,
                "reason": f"student_stuck_{no_answer_streak}_turns",
                "escalation_level": "pure_teach",
            },
        )
    
    if no_answer_streak >= 3:
        # Student has said "I don't know" 3 times. Lead with empathy.
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="empathy_first_then_teach",
            difficulty_adjustment=DifficultyAdjustment.EASIER,
            include_encouragement=True,
            metadata={
                "auto_support": True,
                "reason": f"student_stuck_{no_answer_streak}_turns",
                "escalation_level": "empathy_teach",
            },
        )
    
    # ===== Streak 2 or low confidence — auto-decide approach =====
    
    # 1. Honor explicit student preference
    if analysis.help_preference:
        from app.tutor.turn_analysis_types import HelpPreference
        if analysis.help_preference == HelpPreference.SIMPLE_EXPLANATION:
            return TutorActionPlan(
                kind=TutorActionKind.EXPLAIN_CONCEPT,
                intent_label="auto_simple_explanation",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
                metadata={"auto_support": True, "reason": "student_preference"},
            )
        elif analysis.help_preference == HelpPreference.ONE_EXAMPLE:
            return TutorActionPlan(
                kind=TutorActionKind.EXPLAIN_CONCEPT,
                intent_label="auto_example",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
                metadata={"auto_support": True, "reason": "student_preference"},
            )
        elif analysis.help_preference == HelpPreference.STEP_BY_STEP:
            return TutorActionPlan(
                kind=TutorActionKind.BREAKDOWN_STEP,
                intent_label="auto_step_by_step",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
                metadata={"auto_support": True, "reason": "student_preference"},
            )
    
    # 2. Follow progress evaluator recommendation
    if progress_evaluation and progress_evaluation.recommended_approach != RecommendedApproach.ASK_STUDENT:
        approach = progress_evaluation.recommended_approach
        if approach == RecommendedApproach.EXPLAIN:
            return TutorActionPlan(
                kind=TutorActionKind.EXPLAIN_CONCEPT,
                intent_label="auto_explain_progress_based",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
                metadata={"auto_support": True, "reason": "progress_evaluator"},
            )
        elif approach == RecommendedApproach.EXAMPLE:
            return TutorActionPlan(
                kind=TutorActionKind.EXPLAIN_CONCEPT,
                intent_label="auto_example_progress_based",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
                metadata={"auto_support": True, "reason": "progress_evaluator"},
            )
        elif approach == RecommendedApproach.STEP_BY_STEP:
            return TutorActionPlan(
                kind=TutorActionKind.BREAKDOWN_STEP,
                intent_label="auto_step_by_step_progress_based",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
                metadata={"auto_support": True, "reason": "progress_evaluator"},
            )
    
    # 3. Decide based on error category
    if analysis.error_category == ErrorCategory.CONCEPTUAL:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="auto_explain_conceptual_gap",
            difficulty_adjustment=DifficultyAdjustment.EASIER,
            metadata={"auto_support": True, "reason": "conceptual_error"},
        )
    
    if analysis.error_category == ErrorCategory.PROCEDURE:
        return TutorActionPlan(
            kind=TutorActionKind.BREAKDOWN_STEP,
            intent_label="auto_step_by_step_procedural",
            difficulty_adjustment=DifficultyAdjustment.EASIER,
            metadata={"auto_support": True, "reason": "procedural_error"},
        )
    
    # 4. If frustrated/anxious → concrete example
    if analysis.affect in [AffectSignal.FRUSTRATED, AffectSignal.ANXIOUS]:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="auto_example_for_affect",
            difficulty_adjustment=DifficultyAdjustment.EASIER,
            include_encouragement=True,
            metadata={"auto_support": True, "reason": "negative_affect"},
        )
    
    # 5. Fallback — micro-step support (streak = 2)
    return TutorActionPlan(
        kind=TutorActionKind.BREAKDOWN_STEP,
        intent_label="micro_step_then_check",
        difficulty_adjustment=DifficultyAdjustment.EASIER,
        metadata={
            "auto_support": True,
            "reason": "fallback_auto_support",
        },
    )


# =============================================================================
# Progress-Aware Adaptation
# =============================================================================

def _adapt_for_progress(
    *,
    progress_evaluation: ProgressEvaluation,
    teaching_state: ObjectiveTeachingState,
    analysis: StudentTurnAnalysis,
    performance: ObjectivePerformanceSnapshot,
    config: ObjectiveTeachingConfig,
) -> Optional[TutorActionPlan]:
    """
    Adapt the plan when progress is stalled or regressing.
    Returns None if no special adaptation is needed (let normal flow proceed).
    """
    signal = progress_evaluation.signal
    approach = progress_evaluation.recommended_approach
    
    if signal == ProgressSignal.STALLED:
        # Student is stuck — change approach
        if approach == RecommendedApproach.EXPLAIN:
            return TutorActionPlan(
                kind=TutorActionKind.EXPLAIN_CONCEPT,
                intent_label="progress_aware_pivot_explain",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
                metadata={"reason": "stalled_progress"},
            )
        elif approach == RecommendedApproach.EXAMPLE:
            return TutorActionPlan(
                kind=TutorActionKind.EXPLAIN_CONCEPT,
                intent_label="progress_aware_pivot_example",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
                metadata={"reason": "stalled_progress"},
            )
        elif approach == RecommendedApproach.STEP_BY_STEP:
            return TutorActionPlan(
                kind=TutorActionKind.BREAKDOWN_STEP,
                intent_label="progress_aware_pivot_steps",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
                metadata={"reason": "stalled_progress"},
            )
    
    elif signal == ProgressSignal.REGRESSING:
        # Performance getting worse — go back to explanation
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="progress_aware_reteach",
            difficulty_adjustment=DifficultyAdjustment.EASIER,
            include_encouragement=True,
            metadata={"reason": "regressing_progress"},
        )
    
    return None


# =============================================================================
# Encouragement Logic
# =============================================================================

def _should_encourage(
    analysis: StudentTurnAnalysis,
    performance: ObjectivePerformanceSnapshot,
) -> bool:
    """Determine if the tutor should include encouragement."""
    if analysis.affect in [AffectSignal.FRUSTRATED, AffectSignal.ANXIOUS]:
        return True
    
    if performance.consecutive_errors >= 2:
        return True
    
    if (analysis.kind == TurnKind.ANSWER and 
        analysis.correctness == AnswerCorrectness.INCORRECT and
        performance.incorrect_attempts >= 2):
        return True
    
    return False


# =============================================================================
# State-Specific Planning
# =============================================================================

def _plan_for_not_started(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for NOT_STARTED state."""
    if config.skip_diagnosing:
        return TutorActionPlan(
            kind=TutorActionKind.ASK_QUESTION,
            intent_label="initial_practice_question",
            difficulty_adjustment=DifficultyAdjustment.SAME,
        )
    
    return TutorActionPlan(
        kind=TutorActionKind.ASK_QUESTION,
        intent_label="diagnostic_question",
        difficulty_adjustment=DifficultyAdjustment.SAME,
    )


def _plan_for_diagnosing(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for DIAGNOSING state."""
    # Handle ANSWER turns
    if analysis.kind == TurnKind.ANSWER:
        if analysis.correctness == AnswerCorrectness.NOT_APPLICABLE:
            # Diagnostic response received — acknowledge and move to teaching
            return TutorActionPlan(
                kind=TutorActionKind.EXPLAIN_CONCEPT,
                intent_label="acknowledge_and_introduce_concept",
                metadata={"diagnostic_response_received": True},
            )
        
        if analysis.correctness == AnswerCorrectness.CORRECT:
            if performance.correct_attempts >= 2:
                return TutorActionPlan(
                    kind=TutorActionKind.ASK_QUESTION,
                    intent_label="transition_to_practice",
                    difficulty_adjustment=DifficultyAdjustment.HARDER,
                )
            else:
                return TutorActionPlan(
                    kind=TutorActionKind.ASK_QUESTION,
                    intent_label="diagnostic_question",
                    difficulty_adjustment=DifficultyAdjustment.HARDER,
                )
        
        elif analysis.correctness == AnswerCorrectness.PARTIALLY_CORRECT:
            return TutorActionPlan(
                kind=TutorActionKind.GIVE_HINT,
                intent_label="clarify_partial_understanding",
                difficulty_adjustment=DifficultyAdjustment.SAME,
            )
        
        else:  # INCORRECT
            if analysis.error_category == ErrorCategory.CONCEPTUAL:
                return TutorActionPlan(
                    kind=TutorActionKind.EXPLAIN_CONCEPT,
                    intent_label="explain_prerequisite",
                )
            else:
                return TutorActionPlan(
                    kind=TutorActionKind.BREAKDOWN_STEP,
                    intent_label="show_approach",
                )
    
    # Handle student asking a QUESTION during diagnosis
    if analysis.kind == TurnKind.QUESTION:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="answer_student_question_during_diagnosis",
        )
    
    # Handle meta comments
    if analysis.kind == TurnKind.META:
        if analysis.affect in [AffectSignal.FRUSTRATED, AffectSignal.ANXIOUS]:
            return TutorActionPlan(
                kind=TutorActionKind.ENCOURAGE,
                intent_label="acknowledge_feelings_and_encourage",
            )
        else:
            return TutorActionPlan(
                kind=TutorActionKind.ASK_QUESTION,
                intent_label="gentle_diagnostic_question",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
            )
    
    # Default
    return TutorActionPlan(
        kind=TutorActionKind.ASK_QUESTION,
        intent_label="diagnostic_question",
        difficulty_adjustment=DifficultyAdjustment.SAME,
    )


def _plan_for_exposing(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for EXPOSING state."""
    if analysis.kind == TurnKind.ANSWER:
        if analysis.correctness == AnswerCorrectness.INCORRECT:
            if analysis.error_category == ErrorCategory.CONCEPTUAL:
                return TutorActionPlan(
                    kind=TutorActionKind.EXPLAIN_CONCEPT,
                    intent_label="clarify_misconception",
                )
            else:
                return TutorActionPlan(
                    kind=TutorActionKind.BREAKDOWN_STEP,
                    intent_label="show_step_by_step",
                )
        
        elif analysis.correctness == AnswerCorrectness.PARTIALLY_CORRECT:
            return TutorActionPlan(
                kind=TutorActionKind.GIVE_HINT,
                intent_label="refine_understanding",
                difficulty_adjustment=DifficultyAdjustment.SAME,
            )
        
        else:  # CORRECT
            return TutorActionPlan(
                kind=TutorActionKind.ASK_QUESTION,
                intent_label="guided_practice_question",
                difficulty_adjustment=DifficultyAdjustment.SAME,
            )
    
    if analysis.kind == TurnKind.QUESTION:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="answer_student_question",
        )
    
    if analysis.kind == TurnKind.META:
        if analysis.affect == AffectSignal.FRUSTRATED:
            return TutorActionPlan(
                kind=TutorActionKind.BREAKDOWN_STEP,
                intent_label="simplify_explanation",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
            )
    
    return TutorActionPlan(
        kind=TutorActionKind.ASK_QUESTION,
        intent_label="guided_practice_question",
        difficulty_adjustment=DifficultyAdjustment.SAME,
    )


def _plan_for_supporting(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for SUPPORTING state."""
    return TutorActionPlan(
        kind=TutorActionKind.EXPLAIN_CONCEPT,
        intent_label="simple_explanation_with_example",
        difficulty_adjustment=DifficultyAdjustment.EASIER,
    )


def _plan_for_guided_practice(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for GUIDED_PRACTICE state."""
    recent_accuracy = _calculate_recent_accuracy(performance.recent_answers, window=5)
    has_enough_practice = performance.total_attempts >= config.min_practice_questions
    
    if analysis.kind not in [TurnKind.ANSWER]:
        if analysis.kind == TurnKind.QUESTION:
            return TutorActionPlan(
                kind=TutorActionKind.GIVE_HINT,
                intent_label="answer_with_hint",
            )
        return TutorActionPlan(
            kind=TutorActionKind.ASK_QUESTION,
            intent_label="guided_practice_question",
            difficulty_adjustment=DifficultyAdjustment.SAME,
        )
    
    if analysis.correctness == AnswerCorrectness.CORRECT:
        if has_enough_practice and recent_accuracy >= config.practice_accuracy_threshold:
            return TutorActionPlan(
                kind=TutorActionKind.CHECK_UNDERSTANDING,
                intent_label="transition_to_independent",
            )
        else:
            return TutorActionPlan(
                kind=TutorActionKind.ASK_QUESTION,
                intent_label="guided_practice_question",
                difficulty_adjustment=DifficultyAdjustment.HARDER if recent_accuracy > 0.7 else DifficultyAdjustment.SAME,
            )
    
    elif analysis.correctness == AnswerCorrectness.PARTIALLY_CORRECT:
        return TutorActionPlan(
            kind=TutorActionKind.GIVE_HINT,
            intent_label="scaffold_step",
            difficulty_adjustment=DifficultyAdjustment.SAME,
        )
    
    else:  # INCORRECT
        if analysis.error_category == ErrorCategory.CONCEPTUAL:
            return TutorActionPlan(
                kind=TutorActionKind.BREAKDOWN_STEP,
                intent_label="address_misconception",
            )
        elif analysis.error_category in [ErrorCategory.PROCEDURE, ErrorCategory.MISREADING]:
            return TutorActionPlan(
                kind=TutorActionKind.GIVE_HINT,
                intent_label="scaffold_step",
            )
        else:
            return TutorActionPlan(
                kind=TutorActionKind.GIVE_HINT,
                intent_label="try_different_approach",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
            )


def _plan_for_independent_practice(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for INDEPENDENT_PRACTICE state."""
    recent_accuracy = _calculate_recent_accuracy(performance.recent_answers, window=5)
    
    if analysis.kind != TurnKind.ANSWER:
        if analysis.kind == TurnKind.QUESTION:
            return TutorActionPlan(
                kind=TutorActionKind.GIVE_HINT,
                intent_label="minimal_hint",
            )
        return TutorActionPlan(
            kind=TutorActionKind.ASK_QUESTION,
            intent_label="independent_practice_question",
            difficulty_adjustment=DifficultyAdjustment.SAME,
        )
    
    if analysis.correctness == AnswerCorrectness.CORRECT:
        if recent_accuracy >= config.practice_accuracy_threshold:
            return TutorActionPlan(
                kind=TutorActionKind.CHECK_UNDERSTANDING,
                intent_label="check_mastery",
            )
        else:
            return TutorActionPlan(
                kind=TutorActionKind.ASK_QUESTION,
                intent_label="independent_practice_question",
                difficulty_adjustment=DifficultyAdjustment.SAME,
            )
    
    elif analysis.correctness == AnswerCorrectness.PARTIALLY_CORRECT:
        return TutorActionPlan(
            kind=TutorActionKind.ASK_QUESTION,
            intent_label="independent_practice_question",
            difficulty_adjustment=DifficultyAdjustment.SAME,
        )
    
    else:  # INCORRECT
        if analysis.affect == AffectSignal.FRUSTRATED or performance.consecutive_errors >= 2:
            return TutorActionPlan(
                kind=TutorActionKind.EXPLAIN_CONCEPT,
                intent_label="review_concept",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
            )
        else:
            return TutorActionPlan(
                kind=TutorActionKind.GIVE_HINT,
                intent_label="gentle_redirect",
                difficulty_adjustment=DifficultyAdjustment.EASIER,
            )


def _plan_for_checking(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for CHECKING state."""
    recent_accuracy = _calculate_recent_accuracy(performance.recent_answers, window=config.min_check_questions)
    
    if analysis.kind != TurnKind.ANSWER:
        return TutorActionPlan(
            kind=TutorActionKind.ASK_QUESTION,
            intent_label="mastery_check",
        )
    
    check_attempts = min(len(performance.recent_answers), config.min_check_questions)
    
    if analysis.correctness == AnswerCorrectness.CORRECT:
        if check_attempts >= config.min_check_questions and recent_accuracy >= config.check_accuracy_threshold:
            return TutorActionPlan(
                kind=TutorActionKind.EXPLAIN_CONCEPT,
                intent_label="summary_and_consolidation",
            )
        else:
            return TutorActionPlan(
                kind=TutorActionKind.ASK_QUESTION,
                intent_label="mastery_check",
            )
    
    else:
        return TutorActionPlan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="review_before_recheck",
        )


def _plan_for_consolidating(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for CONSOLIDATING state."""
    if config.skip_consolidating:
        return TutorActionPlan(
            kind=TutorActionKind.SWITCH_OBJECTIVE,
            intent_label="move_to_next",
        )
    
    return TutorActionPlan(
        kind=TutorActionKind.META_COACHING,
        intent_label="summary_and_links",
    )


def _plan_for_mastered(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for MASTERED state."""
    return TutorActionPlan(
        kind=TutorActionKind.SWITCH_OBJECTIVE,
        intent_label="objective_mastered_move_next",
        metadata={"mastered_objective": config.objective_id},
    )


def _plan_for_escalate(
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    config: ObjectiveTeachingConfig,
) -> TutorActionPlan:
    """Planning for ESCALATE state."""
    reasons = []
    
    if performance.total_attempts >= config.max_total_attempts_before_escalate:
        reasons.append("too_many_attempts")
    
    if config.max_consecutive_errors_before_escalate:
        if performance.consecutive_errors >= config.max_consecutive_errors_before_escalate:
            reasons.append("persistent_errors")
    
    if performance.accuracy < 0.3 and performance.total_attempts >= 5:
        reasons.append("low_accuracy")
    
    if analysis.affect == AffectSignal.FRUSTRATED:
        reasons.append("student_frustrated")
    
    escalation_reason = ", ".join(reasons) if reasons else "unknown"
    
    return TutorActionPlan(
        kind=TutorActionKind.ESCALATE,
        escalation_reason=escalation_reason,
        intent_label="escalate_to_human",
        metadata={
            "total_attempts": performance.total_attempts,
            "accuracy": performance.accuracy,
            "consecutive_errors": performance.consecutive_errors,
        },
    )


def _calculate_recent_accuracy(recent_answers: list, window: int = 5) -> float:
    """Calculate accuracy over the last N answers."""
    if not recent_answers:
        return 0.0
    
    recent = recent_answers[-window:]
    correct = sum(1 for ans in recent if ans.get("correct", False))
    return correct / len(recent) if recent else 0.0
