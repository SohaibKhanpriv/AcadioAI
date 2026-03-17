"""
Thinking Loop Nodes for the Tutor LangGraph.

This module implements the core thinking loop nodes that replace the
tutor_turn_placeholder from US-AI-M4-C. Each node is an async function
that takes TutorGraphContext and returns updated context.

The thinking loop consists of:
1. node_analyze_student_turn - Analyze student message using LLM
2. node_update_performance_and_state - Update performance counters and teaching state
3. node_evaluate_progress - Evaluate session progress and recommend approach
4. node_plan_tutor_action - Plan the next pedagogical action
5. node_generate_tutor_response - Generate natural-language response

These nodes append entries to the thinking_trace for visibility.
"""
import logging
from typing import Optional

from app.tutor.graph_context import TutorGraphContext
from app.tutor.enums import ObjectiveTeachingState, AffectSignal, MasteryEstimate
from app.tutor.types import ObjectivePerformanceSnapshot, ObjectiveTeachingConfig, DEFAULT_TUTOR_BEHAVIOR_CONFIG
from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    TurnKind,
    AnswerCorrectness,
    ErrorCategory,
    ConfidenceLevel,
    HelpPreference,
    RequestType,
)
from app.tutor.turn_analysis_service import analyze_student_turn
from app.tutor.turn_analysis_integration import (
    build_snapshot_from_objective_state,
    persist_snapshot_to_state,
)
from app.tutor.performance_snapshot import (
    update_performance_snapshot,
    build_initial_performance_snapshot,
)
from app.tutor.state_machine_integration import (
    apply_objective_state_transition,
    ApplyObjectiveTransitionArgs,
)
from app.tutor.planning_integration import (
    plan_for_current_turn,
    get_default_start_plan,
)
from app.tutor.progress_evaluator import evaluate_progress
from app.tutor.response_generation import generate_tutor_response
from app.tutor.thinking_trace import TutorThinkingStep
from app.tutor.tutor_message import TutorMessage
from app.tutor.exceptions import MissingContextError
from app.repositories import ObjectiveStateRepository

logger = logging.getLogger(__name__)


def _is_low_confidence_message(message: Optional[str]) -> bool:
    """Detect low-confidence responses like 'I don't know' (EN/AR)."""
    if not message:
        return False
    text = message.strip().lower()
    normalized = (
        text.replace("\u2019", "'")
        .replace("`", "'")
        .replace("\u061f", "?")
        .replace("!", " ")
        .replace("?", " ")
        .replace(".", " ")
        .replace(",", " ")
    )
    patterns = [
        "i don't know", "i dont know", "idk", "not sure", "no idea",
        "don't know", "dont know", "i am not sure", "i'm not sure", "i cant", "i can't",
        "\u0645\u0627 \u0628\u0639\u0631\u0641", "\u0645\u0634 \u0639\u0627\u0631\u0641",
        "\u0645\u0627 \u0627\u062f\u0631\u064a", "\u0645\u0627 \u0623\u062f\u0631\u064a",
        "\u0645\u0648 \u0639\u0627\u0631\u0641", "\u0645\u0627 \u0623\u0639\u0631\u0641",
        "\u0644\u0627 \u0623\u0639\u0631\u0641",
        "\u0645\u0627 \u0628\u0639\u0631\u0641\u0634", "\u0645\u0634 \u0639\u0627\u0631\u0641\u0634",
        "\u0645\u0627 \u0641\u0647\u0645\u062a", "\u0645\u0634 \u0641\u0627\u0647\u0645",
        "\u0645\u0648 \u0641\u0627\u0647\u0645", "\u0635\u0639\u0628"
    ]
    if any(p in normalized for p in patterns):
        return True

    token = " ".join(normalized.split())
    short_refusals = {"no", "nope", "nah", "idk", "dk"}
    return token in short_refusals


def _is_non_attempt_message(message: Optional[str]) -> bool:
    """Detect responses that indicate no actual attempt was made."""
    if not message:
        return False
    text = " ".join(message.strip().lower().split())
    non_attempt_markers = {
        "i don't know", "i dont know", "idk", "no idea", "not sure",
        "i can't", "i cant", "don't know", "dont know",
        "no", "nope", "nah", "whatever",
        "\u0645\u0627 \u0628\u0639\u0631\u0641", "\u0645\u0634 \u0639\u0627\u0631\u0641",
        "\u0645\u0627 \u0627\u062f\u0631\u064a", "\u0645\u0627 \u0623\u062f\u0631\u064a",
        "\u0644\u0627 \u0623\u0639\u0631\u0641", "\u0645\u0627 \u0623\u0639\u0631\u0641",
    }
    return text in non_attempt_markers

def _get_locale_from_state(state: TutorGraphContext) -> str:
    """Get locale from TutorGraphContext."""
    locale = "en-US"
    if state.session and state.session.session_metadata:
        metadata = state.session.session_metadata
        locale = metadata.get("locale") or metadata.get("language") or "en-US"
    return locale


def _create_default_analysis() -> StudentTurnAnalysis:
    """Create a default analysis for initial turns (no student message)."""
    return StudentTurnAnalysis(
        kind=TurnKind.OTHER,
        correctness=AnswerCorrectness.NOT_APPLICABLE,
        error_category=ErrorCategory.NONE,
        affect=AffectSignal.NEUTRAL,
        confidence_level=ConfidenceLevel.MEDIUM,
        low_confidence=False,
        help_preference=HelpPreference.UNKNOWN,
        notes="Initial turn - no student message to analyze",
    )


def _get_last_tutor_message(state: TutorGraphContext) -> Optional[str]:
    """Get the tutor's last message from context for analysis."""
    if hasattr(state, 'last_tutor_message') and state.last_tutor_message:
        logger.info(f"Found last_tutor_message in state field: {state.last_tutor_message[:50]}...")
        return state.last_tutor_message
    
    if state.session and state.session.session_metadata:
        msg = state.session.session_metadata.get('last_tutor_message')
        if msg:
            logger.info(f"Found last_tutor_message in session_metadata: {msg[:50]}...")
            return msg
        else:
            logger.warning(f"Session metadata exists but no last_tutor_message. Keys: {list(state.session.session_metadata.keys())}")
    else:
        logger.warning(f"No session or session_metadata available. session={state.session is not None}")
    
    return None


# =============================================================================
# Node: Analyze Student Turn
# =============================================================================

async def node_analyze_student_turn(
    state: TutorGraphContext
) -> TutorGraphContext:
    """
    Analyze the student's message using the LLM classifier.
    """
    if not hasattr(state, 'thinking_trace') or state.thinking_trace is None:
        state.thinking_trace = []
    
    if not state.student_message:
        logger.info(f"No student message, using default analysis for session {state.session_id}")
        state.last_analysis = _create_default_analysis()
        
        state.thinking_trace.append(
            TutorThinkingStep(
                stage="analysis",
                summary="No student message to analyze (initial turn).",
                data={"kind": "other", "correctness": "not_applicable"},
            )
        )
        return state
    
    locale = _get_locale_from_state(state)
    tutor_last_message = _get_last_tutor_message(state)

    # Read expected_answer stored by the previous turn's response generation
    expected_answer = None
    if state.session and state.session.session_metadata:
        expected_answer = state.session.session_metadata.get("expected_answer")
    
    try:
        analysis = await analyze_student_turn(
            tenant_id=state.tenant_id,
            student_message=state.student_message,
            locale=locale,
            expected_answer=expected_answer,
            tutor_last_message=tutor_last_message,
            objective_id=state.current_objective_id,
            objective_title=state.objective_labels.get(state.current_objective_id or "", ""),
            lesson_id=state.lesson_id,
            chat_history=state.chat_history,
        )
    except Exception as e:
        logger.error(f"Analysis failed, using fallback: {str(e)}", exc_info=True)
        analysis = StudentTurnAnalysis(
            kind=TurnKind.OTHER,
            correctness=AnswerCorrectness.NOT_APPLICABLE,
            error_category=ErrorCategory.OTHER,
            affect=AffectSignal.NEUTRAL,
            confidence_level=ConfidenceLevel.MEDIUM,
            low_confidence=False,
            help_preference=HelpPreference.UNKNOWN,
            notes=f"Fallback analysis due to error: {str(e)}",
        )
    
    state.last_analysis = analysis

    lexical_low_confidence = _is_low_confidence_message(state.student_message)
    state.low_confidence = bool(analysis.low_confidence) or lexical_low_confidence

    # Normalize explicit non-attempt turns
    if (
        state.low_confidence
        and analysis.kind == TurnKind.ANSWER
        and analysis.correctness == AnswerCorrectness.INCORRECT
        and _is_non_attempt_message(state.student_message)
    ):
        analysis.correctness = AnswerCorrectness.NOT_APPLICABLE
        analysis.error_category = ErrorCategory.NONE
        if analysis.notes:
            analysis.notes = f"{analysis.notes} | normalized_to_non_attempt"
        else:
            analysis.notes = "normalized_to_non_attempt"

    if state.low_confidence:
        state.no_answer_streak += 1
    else:
        state.no_answer_streak = 0
    
    # Append thinking trace
    trace_data = {
        "kind": analysis.kind.value,
        "correctness": analysis.correctness.value,
        "error_category": analysis.error_category.value,
        "affect": analysis.affect.value,
        "confidence_level": analysis.confidence_level.value if analysis.confidence_level else None,
        "help_preference": analysis.help_preference.value if analysis.help_preference else None,
        "low_confidence": state.low_confidence,
        "no_answer_streak": state.no_answer_streak,
    }
    if analysis.request_type:
        trace_data["request_type"] = analysis.request_type.value
    
    state.thinking_trace.append(
        TutorThinkingStep(
            stage="analysis",
            summary="Analyzed the student message and classified correctness and affect.",
            data=trace_data,
        )
    )
    
    logger.info(
        f"Analysis complete: session={state.session_id}, "
        f"kind={analysis.kind.value}, correctness={analysis.correctness.value}"
    )
    
    return state


# =============================================================================
# Node: Update Performance and State
# =============================================================================

async def node_update_performance_and_state(
    state: TutorGraphContext
) -> TutorGraphContext:
    """
    Update performance snapshot and apply state machine transition.
    """
    if not state.current_objective_id:
        logger.warning("No current objective, skipping performance update")
        return state
    
    current_obj_state = state.objectives.get(state.current_objective_id)
    if not current_obj_state:
        logger.warning(f"ObjectiveState not found for {state.current_objective_id}")
        return state
    
    analysis = state.last_analysis
    if not analysis:
        logger.warning("No analysis found, creating default")
        analysis = _create_default_analysis()
        state.last_analysis = analysis
    
    previous_snapshot = build_snapshot_from_objective_state(current_obj_state)
    
    updated_snapshot = update_performance_snapshot(
        previous=previous_snapshot,
        analysis=analysis,
        max_recent=10,
    )
    
    state.current_performance_snapshot = updated_snapshot
    
    persist_snapshot_to_state(current_obj_state, updated_snapshot)
    
    config = state.objective_config or ObjectiveTeachingConfig(
        objective_id=state.current_objective_id
    )
    
    objective_repo = ObjectiveStateRepository(state.db_session)
    
    args = ApplyObjectiveTransitionArgs(
        tenant_id=state.tenant_id,
        session_id=state.session.id,
        objective_id=state.current_objective_id,
        performance=updated_snapshot,
        objective_config=config,
    )
    
    updated_model = await apply_objective_state_transition(
        repo=objective_repo,
        args=args,
    )
    
    terminal_states = {ObjectiveTeachingState.MASTERED.value, ObjectiveTeachingState.ESCALATE.value}
    if updated_model.state not in terminal_states:
        if state.no_answer_streak >= DEFAULT_TUTOR_BEHAVIOR_CONFIG.max_no_answer_streak_before_escalate:
            updated_model.state = ObjectiveTeachingState.ESCALATE.value
            updated_model.mastery_estimate = MasteryEstimate.LOW.value
            await objective_repo.save_objective_state(updated_model)
            logger.info(f"Escalating objective {state.current_objective_id}: no_answer_streak={state.no_answer_streak}")
        elif state.no_answer_streak >= 2:
            updated_model.state = ObjectiveTeachingState.SUPPORTING.value
            await objective_repo.save_objective_state(updated_model)

    await state.db_session.commit()
    
    current_obj_state.state = updated_model.state
    current_obj_state.mastery_estimate = updated_model.mastery_estimate
    current_obj_state.questions_asked = updated_model.questions_asked
    current_obj_state.questions_correct = updated_model.questions_correct
    current_obj_state.questions_incorrect = updated_model.questions_incorrect

    # If the current objective just became terminal, check whether the whole
    # lesson is now complete so the response generator can craft a closing reply.
    if updated_model.state in terminal_states:
        all_terminal = all(
            obj.state in terminal_states
            for obj in state.objectives.values()
        )
        if all_terminal:
            state.lesson_complete = True
            logger.info(
                f"All objectives terminal — marking lesson_complete on this turn "
                f"(session={state.session_id})"
            )
    
    state.thinking_trace.append(
        TutorThinkingStep(
            stage="performance_update",
            summary="Updated performance snapshot and teaching state for the current objective.",
            data={
                "teaching_state": updated_model.state,
                "total_attempts": updated_snapshot.total_attempts,
                "correct_attempts": updated_snapshot.correct_attempts,
                "incorrect_attempts": updated_snapshot.incorrect_attempts,
            },
        )
    )
    
    logger.info(
        f"Performance updated: session={state.session_id}, "
        f"state={updated_model.state}, "
        f"attempts={updated_snapshot.total_attempts}"
    )
    
    return state


# =============================================================================
# Node: Evaluate Progress (NEW)
# =============================================================================

async def node_evaluate_progress(
    state: TutorGraphContext
) -> TutorGraphContext:
    """
    Evaluate session progress and recommend teaching approach.
    
    This node:
    - Runs the lightweight progress evaluator
    - Stores ProgressEvaluation in state.progress_evaluation
    - Appends a thinking trace entry
    """
    performance = state.current_performance_snapshot
    if not performance:
        performance = build_initial_performance_snapshot()
    
    analysis = state.last_analysis
    if not analysis:
        analysis = _create_default_analysis()
    
    progress_eval = evaluate_progress(
        performance=performance,
        analysis=analysis,
        chat_history=state.chat_history,
    )
    
    state.progress_evaluation = progress_eval
    
    state.thinking_trace.append(
        TutorThinkingStep(
            stage="progress_evaluation",
            summary=f"Evaluated progress: {progress_eval.signal.value}, approach: {progress_eval.recommended_approach.value}",
            data={
                "signal": progress_eval.signal.value,
                "recommended_approach": progress_eval.recommended_approach.value,
                "reasoning": progress_eval.reasoning,
            },
        )
    )
    
    logger.info(
        f"Progress evaluated: session={state.session_id}, "
        f"signal={progress_eval.signal.value}, "
        f"approach={progress_eval.recommended_approach.value}"
    )
    
    return state


# =============================================================================
# Node: Plan Tutor Action
# =============================================================================

async def node_plan_tutor_action(
    state: TutorGraphContext
) -> TutorGraphContext:
    """
    Plan the next tutor action based on state and performance.
    """
    if not state.current_objective_id:
        logger.info("No current objective, using default start plan")
        state.tutor_action_plan = get_default_start_plan("unknown")
        return state
    
    performance = state.current_performance_snapshot
    if not performance:
        performance = build_initial_performance_snapshot()
        state.current_performance_snapshot = performance
    
    analysis = state.last_analysis
    if not analysis:
        analysis = _create_default_analysis()
        state.last_analysis = analysis
    
    try:
        plan = plan_for_current_turn(
            state=state,
            performance=performance,
            analysis=analysis,
        )
    except MissingContextError as e:
        logger.warning(f"Missing context for planning: {e}, using default plan")
        plan = get_default_start_plan(state.current_objective_id)
    
    # If the lesson was completed this turn (all objectives terminal),
    # override the plan to END_LESSON so the LLM crafts a proper closing.
    if state.lesson_complete:
        from app.tutor.action_schema import TutorActionKind, TutorActionPlan as _TAP
        plan = _TAP(
            kind=TutorActionKind.END_LESSON,
            intent_label="lesson_mastered_congratulate",
            metadata={"reason": "all_objectives_terminal"},
        )

    state.tutor_action_plan = plan

    # Persist MCQ mode flag to session metadata for next turn
    if state.session and state.session.session_metadata is not None:
        meta = dict(state.session.session_metadata)
        if plan.metadata.get("set_mcq_mode"):
            meta["mcq_mode"] = True
        if plan.metadata.get("exit_mcq"):
            meta["mcq_mode"] = False
        state.session.session_metadata = meta
    
    state.thinking_trace.append(
        TutorThinkingStep(
            stage="planning",
            summary="Planned the next tutor action based on state and performance.",
            data={
                "action_kind": plan.kind.value,
                "intent_label": plan.intent_label,
                "difficulty_adjustment": plan.difficulty_adjustment.value if plan.difficulty_adjustment else None,
            },
        )
    )
    
    logger.info(
        f"Action planned: session={state.session_id}, "
        f"action={plan.kind.value}, intent={plan.intent_label}"
    )
    
    return state


# =============================================================================
# Node: Generate Tutor Response
# =============================================================================

async def node_generate_tutor_response(
    state: TutorGraphContext
) -> TutorGraphContext:
    """
    Generate a natural-language tutor message from the action plan.
    """
    locale = _get_locale_from_state(state)
    
    lesson_context = {
        "lesson_id": state.lesson_id,
        "all_objectives": [
            {
                "id": obj_id,
                "title": state.objective_labels.get(obj_id, obj_id),
                "state": state.objectives[obj_id].state if obj_id in state.objectives else "unknown",
                "is_current": obj_id == state.current_objective_id,
            }
            for obj_id in state.objective_ids
        ] if state.objective_ids else [],
    }
    
    objective_context = {
        "objective_id": state.current_objective_id,
        "title": state.objective_labels.get(state.current_objective_id or "", ""),
    }
    
    # Add current objective performance if available
    if state.current_objective_id and state.current_objective_id in state.objectives:
        obj = state.objectives[state.current_objective_id]
        objective_context["teaching_state"] = obj.state
        objective_context["questions_asked"] = obj.questions_asked
        objective_context["questions_correct"] = obj.questions_correct
    
    action_plan = state.tutor_action_plan
    if not action_plan:
        action_plan = get_default_start_plan(state.current_objective_id or "unknown")
        state.tutor_action_plan = action_plan
    
    history_for_prompt = list(state.chat_history)
    if state.student_message:
        history_for_prompt.append({"role": "student", "content": state.student_message})

    grade_band = None
    skill_level = None
    if state.student_profile:
        grade_band = getattr(state.student_profile, "grade_band", None) or (state.session and (state.session.session_metadata or {}).get("onboarding", {}).get("answers", {}).get("grade"))
        skill_level = getattr(state.student_profile, "skill_level", None) or (state.session and (state.session.session_metadata or {}).get("onboarding", {}).get("answers", {}).get("level"))

    message = await generate_tutor_response(
        tenant_id=state.tenant_id,
        locale=locale,
        action_plan=action_plan,
        lesson_context=lesson_context,
        objective_context=objective_context,
        student_analysis=state.last_analysis,
        chat_history=history_for_prompt,
        progress_evaluation=state.progress_evaluation,
        student_message=state.student_message,
        last_tutor_message=_get_last_tutor_message(state),
        grade_band=grade_band,
        skill_level=skill_level,
    )
    
    state.tutor_message = message
    state.tutor_reply = message.text

    # Store expected_answer in session metadata so the next turn's analysis can use it
    ea = (message.metadata or {}).get("expected_answer")
    if state.session and state.session.session_metadata is not None:
        meta = dict(state.session.session_metadata)
        meta["expected_answer"] = ea  # None clears it when no question was asked
        state.session.session_metadata = meta
    
    state.thinking_trace.append(
        TutorThinkingStep(
            stage="response_generation",
            summary="Generated a tutor message consistent with the action plan.",
            data={
                "length_chars": len(message.text),
                "expected_answer": ea,
            },
        )
    )
    
    logger.info(
        f"Response generated: session={state.session_id}, "
        f"length={len(message.text)} chars"
    )
    
    return state
