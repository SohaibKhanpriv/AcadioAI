"""
Progress Evaluator.

Lightweight rule-based evaluation of session progress to inform the planner.
Detects stalls, regressions, and recommends teaching approach changes.
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any

from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    TurnKind,
    AnswerCorrectness,
    ErrorCategory,
)
from app.tutor.types import ObjectivePerformanceSnapshot
from app.tutor.enums import AffectSignal


class ProgressSignal(str, Enum):
    """Overall progress direction for the current objective."""
    ADVANCING = "advancing"       # Student is making progress
    STALLED = "stalled"           # No progress in recent turns
    REGRESSING = "regressing"     # Performance is getting worse


class RecommendedApproach(str, Enum):
    """AI-decided teaching approach."""
    EXPLAIN = "explain"           # Give a clear explanation
    EXAMPLE = "example"           # Show a concrete example
    STEP_BY_STEP = "step_by_step" # Break down into steps
    CONTINUE = "continue"        # Current approach is working, keep going
    ASK_STUDENT = "ask_student"   # Genuinely uncertain — ask the student


@dataclass
class ProgressEvaluation:
    """Result of evaluating session progress."""
    signal: ProgressSignal
    recommended_approach: RecommendedApproach
    reasoning: str  # Brief explanation for logging/debugging


def evaluate_progress(
    *,
    performance: ObjectivePerformanceSnapshot,
    analysis: StudentTurnAnalysis,
    chat_history: Optional[List[Dict[str, Any]]] = None,
) -> ProgressEvaluation:
    """
    Evaluate session progress and recommend teaching approach.
    
    This is a pure, rule-based function (no LLM calls).
    
    Uses:
    - Recent answer accuracy trend
    - Error category consistency (same error = conceptual gap)
    - Student affect signals
    - Whether the conversation is looping
    
    Returns:
        ProgressEvaluation with signal and recommended approach
    """
    recent = performance.recent_answers or []
    
    # ----- Detect progress signal -----
    signal = _detect_progress_signal(recent, performance)
    
    # ----- Decide recommended approach -----
    approach = _decide_approach(
        signal=signal,
        analysis=analysis,
        recent=recent,
        performance=performance,
    )
    
    # ----- Build reasoning -----
    reasoning = _build_reasoning(signal, approach, recent, analysis)
    
    return ProgressEvaluation(
        signal=signal,
        recommended_approach=approach,
        reasoning=reasoning,
    )


def _detect_progress_signal(
    recent: List[Dict[str, Any]],
    performance: ObjectivePerformanceSnapshot,
) -> ProgressSignal:
    """Detect if the student is advancing, stalled, or regressing."""
    
    if len(recent) < 2:
        # Not enough data — assume advancing
        return ProgressSignal.ADVANCING
    
    last_3 = recent[-3:] if len(recent) >= 3 else recent
    last_3_correct = sum(1 for a in last_3 if a.get("correct", False))
    last_3_accuracy = last_3_correct / len(last_3)
    
    # Check for regression: if last 3 are all wrong after having some correct earlier
    if len(recent) >= 4:
        earlier = recent[:-3]
        earlier_correct = sum(1 for a in earlier if a.get("correct", False))
        earlier_accuracy = earlier_correct / len(earlier) if earlier else 0
        
        if earlier_accuracy >= 0.5 and last_3_accuracy <= 0.33:
            return ProgressSignal.REGRESSING
    
    # Check for stall: low accuracy over last 3-4 turns
    if last_3_accuracy <= 0.33 and performance.consecutive_errors >= 2:
        return ProgressSignal.STALLED
    
    return ProgressSignal.ADVANCING


def _decide_approach(
    *,
    signal: ProgressSignal,
    analysis: StudentTurnAnalysis,
    recent: List[Dict[str, Any]],
    performance: ObjectivePerformanceSnapshot,
) -> RecommendedApproach:
    """
    Auto-decide the best teaching approach based on context.
    
    Priority:
    1. If student explicitly requested something → honor it
    2. If error is conceptual → explain
    3. If error is procedural → step_by_step
    4. If student is frustrated/anxious → example (concrete, less abstract)
    5. If progressing well → continue
    6. If genuinely ambiguous → ask_student
    """
    
    # 1. If student has a help_preference, honor it
    if analysis.help_preference:
        from app.tutor.turn_analysis_types import HelpPreference
        pref_map = {
            HelpPreference.SIMPLE_EXPLANATION: RecommendedApproach.EXPLAIN,
            HelpPreference.ONE_EXAMPLE: RecommendedApproach.EXAMPLE,
            HelpPreference.STEP_BY_STEP: RecommendedApproach.STEP_BY_STEP,
        }
        if analysis.help_preference in pref_map:
            return pref_map[analysis.help_preference]
    
    # 2. If student made a request, honor the request_type
    if analysis.kind == TurnKind.REQUEST and analysis.request_type:
        from app.tutor.turn_analysis_types import RequestType
        request_map = {
            RequestType.EXPLAIN: RecommendedApproach.EXPLAIN,
            RequestType.EXAMPLE: RecommendedApproach.EXAMPLE,
            RequestType.STEP_BY_STEP: RecommendedApproach.STEP_BY_STEP,
            RequestType.REPEAT: RecommendedApproach.EXPLAIN,
        }
        if analysis.request_type in request_map:
            return request_map[analysis.request_type]
    
    # 3. If advancing well, keep going
    if signal == ProgressSignal.ADVANCING:
        return RecommendedApproach.CONTINUE
    
    # 4. Decide based on error patterns
    recent_errors = [
        a.get("error_category", "none")
        for a in recent[-3:]
        if not a.get("correct", False)
    ]
    
    if recent_errors:
        # Check for consistent conceptual errors
        conceptual_count = sum(1 for e in recent_errors if e == "conceptual")
        procedural_count = sum(1 for e in recent_errors if e == "procedure")
        
        if conceptual_count >= 2:
            return RecommendedApproach.EXPLAIN
        if procedural_count >= 2:
            return RecommendedApproach.STEP_BY_STEP
    
    # Check current turn's error
    if analysis.kind == TurnKind.ANSWER and analysis.correctness == AnswerCorrectness.INCORRECT:
        if analysis.error_category == ErrorCategory.CONCEPTUAL:
            return RecommendedApproach.EXPLAIN
        elif analysis.error_category == ErrorCategory.PROCEDURE:
            return RecommendedApproach.STEP_BY_STEP
    
    # 5. If frustrated/anxious, use a concrete example (less abstract)
    if analysis.affect in [AffectSignal.FRUSTRATED, AffectSignal.ANXIOUS]:
        return RecommendedApproach.EXAMPLE
    
    # 6. Stalled with no clear error pattern — try example
    if signal == ProgressSignal.STALLED:
        return RecommendedApproach.EXAMPLE
    
    # 7. Regressing — explain from scratch
    if signal == ProgressSignal.REGRESSING:
        return RecommendedApproach.EXPLAIN
    
    return RecommendedApproach.CONTINUE


def _build_reasoning(
    signal: ProgressSignal,
    approach: RecommendedApproach,
    recent: List[Dict[str, Any]],
    analysis: StudentTurnAnalysis,
) -> str:
    """Build a brief reasoning string for logging."""
    parts = [f"signal={signal.value}"]
    
    if recent:
        last_3 = recent[-3:] if len(recent) >= 3 else recent
        accuracy = sum(1 for a in last_3 if a.get("correct")) / len(last_3)
        parts.append(f"recent_accuracy={accuracy:.0%}")
    
    parts.append(f"affect={analysis.affect.value}")
    
    if analysis.kind == TurnKind.ANSWER and analysis.correctness != AnswerCorrectness.NOT_APPLICABLE:
        parts.append(f"correctness={analysis.correctness.value}")
        if analysis.error_category != ErrorCategory.NONE:
            parts.append(f"error={analysis.error_category.value}")
    
    parts.append(f"→ approach={approach.value}")
    
    return ", ".join(parts)
