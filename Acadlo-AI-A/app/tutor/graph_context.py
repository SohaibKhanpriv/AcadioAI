"""
Graph context for the Tutor LangGraph.

This module defines the state object that flows through all LangGraph nodes.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Forward references to persistence models
from app.db.models import TutorSession, ObjectiveState, StudentProfile
from app.tutor.types import LessonTeachingConfig, ObjectiveTeachingConfig


@dataclass
class TutorGraphContext:
    """
    Context object that flows through all LangGraph nodes.
    
    This is the "state" of the LangGraph for the tutor engine.
    It holds all runtime data needed to execute a tutoring turn.
    """
    # ===== Identity and tenancy =====
    tenant_id: str
    session_id: Optional[str] = None
    
    # ===== Organization / scopes =====
    ou_id: Optional[str] = None
    context_scopes: List[str] = field(default_factory=list)  # For RAG visibility filtering
    
    # ===== Lesson & objective context =====
    program_id: Optional[str] = None
    lesson_id: str = ""
    objective_ids: List[str] = field(default_factory=list)
    objective_labels: Dict[str, str] = field(default_factory=dict)  # objective_id -> human-readable objective text
    current_objective_id: Optional[str] = None
    
    # ===== Student & region =====
    student_id: str = ""
    region_id: Optional[str] = None
    
    # ===== Runtime models (loaded from DB) =====
    session: Optional[TutorSession] = None
    objectives: Dict[str, ObjectiveState] = field(default_factory=dict)  # keyed by objective_id
    student_profile: Optional[StudentProfile] = None
    
    # ===== Teaching configuration =====
    lesson_config: Optional[LessonTeachingConfig] = None
    objective_config: Optional[ObjectiveTeachingConfig] = None  # for current_objective_id
    
    # ===== Turn-level data (set on each /start or /continue call) =====
    student_message: Optional[str] = None  # input from student this turn
    last_tutor_message: Optional[str] = None  # The tutor's previous response (for analysis context)
    chat_history: List[Dict[str, str]] = field(default_factory=list)  # recent chat memory
    
    # ===== Analysis & Planning (set during thinking loop) =====
    last_analysis: Optional[Any] = None  # StudentTurnAnalysis from M4-D
    tutor_action_plan: Optional[Any] = None  # TutorActionPlan from M4-E
    current_performance_snapshot: Optional[Any] = None  # ObjectivePerformanceSnapshot
    progress_evaluation: Optional[Any] = None  # ProgressEvaluation from progress_evaluator
    
    # ===== Response Generation (set during thinking loop) =====
    tutor_message: Optional[Any] = None  # TutorMessage from M4-F
    
    # ===== Thinking Trace (for debugging/visibility) =====
    # Re-initialized per turn, holds TutorThinkingStep entries
    thinking_trace: List[Any] = field(default_factory=list)
    
    # ===== Output / status for this turn =====
    tutor_reply: Optional[str] = None
    lesson_complete: bool = False
    
    # ===== Internal flags =====
    is_new_session: bool = False  # True if this is a session start
    low_confidence: bool = False  # True if student signals low confidence this turn
    no_answer_streak: int = 0  # Count of consecutive "I don't know" style turns
    
    # ===== Locale hint for new sessions =====
    # This is used during session creation to store the locale in session_metadata
    locale_hint: Optional[str] = None  # BCP-47 locale code (e.g. 'ar-JO', 'en-US')
    
    # ===== Database session (injected, not serialized) =====
    db_session: Optional[Any] = None  # AsyncSession, passed at runtime

    # ===== Onboarding (used by onboarding_check node) =====
    onboarding_required: List[str] = field(default_factory=list)  # question keys still needed
    onboarding_answers: Dict[str, str] = field(default_factory=dict)  # collected answers
    next_onboarding_question: Optional[str] = None  # next key to ask, or None if done
    onboarding_complete: bool = False  # True when we can proceed to teaching / resolve_lesson
    needs_lesson_generation: bool = False  # True when lesson_id is pending and we need to resolve


@dataclass
class TutorStartParams:
    """Parameters for starting a new tutoring session"""
    tenant_id: str
    student_id: str
    lesson_id: str
    objective_ids: List[str]
    objective_labels: Dict[str, str] = field(default_factory=dict)
    ou_id: Optional[str] = None
    region_id: Optional[str] = None
    program_id: Optional[str] = None
    context_scopes: List[str] = field(default_factory=list)
    lesson_config: Optional[LessonTeachingConfig] = None
    initial_student_message: Optional[str] = None  # optional first message from student
    locale: Optional[str] = None  # BCP-47 locale code (e.g. 'ar-JO', 'en-US')


@dataclass
class TutorContinueParams:
    """Parameters for continuing an existing tutoring session"""
    tenant_id: str
    session_id: str
    student_message: str


@dataclass
class TutorTurnResult:
    """Result of a tutoring turn"""
    tenant_id: str
    session_id: str
    lesson_id: str
    current_objective_id: Optional[str]
    tutor_reply: str
    lesson_complete: bool
    # Optional thinking trace (when requested via API)
    thinking_trace: Optional[List[Dict[str, Any]]] = None


