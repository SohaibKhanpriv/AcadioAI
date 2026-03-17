"""Tutor Runtime Engine module"""
from app.tutor.enums import (
    TutorSessionStatus,
    ObjectiveTeachingState,
    MasteryEstimate,
    PaceEstimate,
    EngagementEstimate,
    AffectSignal
)
from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    TurnKind,
    AnswerCorrectness,
    ErrorCategory,
    ReasoningQuality
)
from app.tutor.types import (
    ObjectivePerformanceSnapshot,
    ObjectiveTeachingConfig,
    LessonTeachingConfig,
    ObjectiveStateTransitionInput,
    ObjectiveStateTransitionOutput
)
from app.tutor.action_schema import (
    TutorActionKind,
    TutorActionPlan,
    DifficultyAdjustment
)
from app.tutor.state_machine import compute_objective_state_transition
from app.tutor.state_machine_integration import (
    apply_objective_state_transition,
    build_performance_snapshot_from_state,
    ApplyObjectiveTransitionArgs
)
from app.tutor.graph_context import (
    TutorGraphContext,
    TutorStartParams,
    TutorContinueParams,
    TutorTurnResult
)
from app.tutor.runner import run_tutor_start, run_tutor_turn
from app.tutor.performance_snapshot import (
    update_performance_snapshot,
    build_initial_performance_snapshot
)
from app.tutor.turn_analysis_service import analyze_student_turn
from app.tutor.turn_analysis_integration import (
    analyze_turn_and_update_snapshot,
    build_snapshot_from_objective_state,
    persist_snapshot_to_state
)
from app.tutor.planning import plan_next_tutor_action
from app.tutor.planning_integration import (
    plan_for_current_turn,
    get_default_start_plan,
    should_end_lesson,
    get_next_objective_id
)
from app.tutor.exceptions import (
    TutorRuntimeError,
    MissingContextError,
    TurnAnalysisError,
    ObjectiveStateNotFoundError
)
# M4-F: Tutor Message and Response Generation
from app.tutor.tutor_message import TutorMessage
from app.tutor.thinking_trace import (
    TutorThinkingStep,
    serialize_thinking_trace
)
from app.tutor.response_generation import generate_tutor_response
from app.tutor.thinking_loop_nodes import (
    node_analyze_student_turn,
    node_update_performance_and_state,
    node_plan_tutor_action,
    node_generate_tutor_response
)

__all__ = [
    # Enums
    "TutorSessionStatus",
    "ObjectiveTeachingState",
    "MasteryEstimate",
    "PaceEstimate",
    "EngagementEstimate",
    "AffectSignal",
    # Turn Analysis Types
    "StudentTurnAnalysis",
    "TurnKind",
    "AnswerCorrectness",
    "ErrorCategory",
    "ReasoningQuality",
    # Types
    "ObjectivePerformanceSnapshot",
    "ObjectiveTeachingConfig",
    "LessonTeachingConfig",
    "ObjectiveStateTransitionInput",
    "ObjectiveStateTransitionOutput",
    # Action Schema (M4-E)
    "TutorActionKind",
    "TutorActionPlan",
    "DifficultyAdjustment",
    # State Machine
    "compute_objective_state_transition",
    # State Machine Integration
    "apply_objective_state_transition",
    "build_performance_snapshot_from_state",
    "ApplyObjectiveTransitionArgs",
    # Graph Context
    "TutorGraphContext",
    "TutorStartParams",
    "TutorContinueParams",
    "TutorTurnResult",
    # Runners
    "run_tutor_start",
    "run_tutor_turn",
    # Performance Snapshot
    "update_performance_snapshot",
    "build_initial_performance_snapshot",
    # Turn Analysis
    "analyze_student_turn",
    "analyze_turn_and_update_snapshot",
    "build_snapshot_from_objective_state",
    "persist_snapshot_to_state",
    # Planning (M4-E)
    "plan_next_tutor_action",
    "plan_for_current_turn",
    "get_default_start_plan",
    "should_end_lesson",
    "get_next_objective_id",
    # Exceptions
    "TutorRuntimeError",
    "MissingContextError",
    "TurnAnalysisError",
    "ObjectiveStateNotFoundError",
    # M4-F: Tutor Message and Response Generation
    "TutorMessage",
    "TutorThinkingStep",
    "serialize_thinking_trace",
    "generate_tutor_response",
    # M4-F: Thinking Loop Nodes
    "node_analyze_student_turn",
    "node_update_performance_and_state",
    "node_plan_tutor_action",
    "node_generate_tutor_response",
]
