"""
Type definitions for the Tutor Runtime Engine.

These types are used for state machine transitions and performance tracking.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from app.tutor.enums import ObjectiveTeachingState, MasteryEstimate, AffectSignal


@dataclass
class ObjectivePerformanceSnapshot:
    """
    Snapshot of student performance on an objective.
    
    This is a pure data class used as input to the state machine.
    It represents the current state of a student's work on an objective.
    """
    total_attempts: int
    correct_attempts: int
    incorrect_attempts: int
    recent_answers: List[Dict[str, Any]]  # e.g., [{"correct": True, "error_type": "place_value"}, ...]
    recent_affect: Optional[AffectSignal] = None  # Using AffectSignal enum
    
    @property
    def accuracy(self) -> float:
        """Calculate accuracy as correct / total (0.0 if no attempts)"""
        if self.total_attempts == 0:
            return 0.0
        return self.correct_attempts / self.total_attempts
    
    @property
    def recent_accuracy(self, window: int = 5) -> float:
        """Calculate accuracy over the last N answers"""
        if not self.recent_answers:
            return 0.0
        
        recent = self.recent_answers[-window:]
        correct = sum(1 for ans in recent if ans.get("correct", False))
        return correct / len(recent) if recent else 0.0
    
    @property
    def consecutive_errors(self) -> int:
        """Count consecutive incorrect answers from the end"""
        count = 0
        for ans in reversed(self.recent_answers):
            if ans.get("correct", False):
                break
            count += 1
        return count

    @property
    def consecutive_correct(self) -> int:
        """Count consecutive correct answers from the end"""
        count = 0
        for ans in reversed(self.recent_answers):
            if not ans.get("correct", False):
                break
            count += 1
        return count


@dataclass
class ObjectiveTeachingConfig:
    """
    Configuration for teaching behavior on a single objective.
    
    These parameters control when transitions happen in the state machine.
    """
    objective_id: str
    
    # Minimum number of practice questions before we can check mastery
    min_practice_questions: int = 3
    
    # Required accuracy over recent questions to consider moving forward
    practice_accuracy_threshold: float = 0.7  # 70%
    
    # Minimum number of "check" questions to decide mastery
    min_check_questions: int = 2
    
    # Required accuracy in checking phase to declare mastery
    check_accuracy_threshold: float = 0.8  # 80%
    
    # Maximum number of total attempts before considering escalation
    max_total_attempts_before_escalate: int = 12
    
    # Optional: maximum consecutive incorrect answers before escalation flag
    max_consecutive_errors_before_escalate: Optional[int] = 4
    
    # Optional: flags to skip some phases (e.g., skip diagnosing for trivial objectives)
    skip_diagnosing: bool = False
    skip_consolidating: bool = False


@dataclass
class LessonTeachingConfig:
    """
    Configuration for all objectives in a lesson.
    
    Maps objective IDs to their configurations.
    """
    lesson_id: str
    objective_configs: Dict[str, ObjectiveTeachingConfig]
    
    def get_config(self, objective_id: str) -> ObjectiveTeachingConfig:
        """Get config for an objective, or return default"""
        if objective_id in self.objective_configs:
            return self.objective_configs[objective_id]
        
        # Return default config
        return ObjectiveTeachingConfig(objective_id=objective_id)


@dataclass
class TutorBehaviorConfig:
    """
    Named constants for tutor behavior thresholds.
    Enables easy tuning without magic numbers; can be overridden per lesson/tenant later.
    """
    mcq_trigger_on_guessing: bool = True
    wrong_streak_simplify_threshold: int = 2
    mcq_exit_on_correct: bool = True
    correct_answer_difficulty_bump: bool = True
    max_onboarding_questions: int = 4
    chat_history_max_messages: int = 12
    max_no_answer_streak_before_escalate: int = 6
    consecutive_correct_for_mastery: int = 5
    consecutive_wrong_for_escalate: int = 5


# Default instance for use across the tutor
DEFAULT_TUTOR_BEHAVIOR_CONFIG = TutorBehaviorConfig()


@dataclass
class ObjectiveStateTransitionInput:
    """Input to the state transition function"""
    current_state: ObjectiveTeachingState
    objective_config: ObjectiveTeachingConfig
    performance: ObjectivePerformanceSnapshot


@dataclass
class ObjectiveStateTransitionOutput:
    """Output from the state transition function"""
    next_state: ObjectiveTeachingState
    mastery_estimate: MasteryEstimate
    escalate_flag: bool
    reasoning: str  # Human-readable explanation for debugging
