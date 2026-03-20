"""
Enums for the Tutor Runtime Engine.

Defines strongly-typed enumerations for session status, teaching states,
mastery estimates, pace, and engagement levels.
"""
from enum import Enum


class TutorSessionStatus(str, Enum):
    """
    Status of a tutoring session.
    
    - ACTIVE: Session is currently in progress
    - COMPLETED: All objectives completed successfully
    - ABORTED: Session was terminated early
    """
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"


class ObjectiveTeachingState(str, Enum):
    """
    Teaching state for a single learning objective.
    
    Represents the pedagogical phase of instruction:
    - NOT_STARTED: Objective not yet begun
    - DIAGNOSING: Probing prior knowledge
    - EXPOSING: Explaining concepts and showing examples
    - SUPPORTING: Extra scaffolding when student is stuck or unsure
    - GUIDED_PRACTICE: Practice with hints and step-by-step guidance
    - INDEPENDENT_PRACTICE: Practice with minimal help
    - CHECKING: Focused mastery check questions
    - CONSOLIDATING: Summarization and reinforcement
    - MASTERED: Objective successfully learned
    - ESCALATE: Requires human intervention
    """
    NOT_STARTED = "not_started"
    DIAGNOSING = "diagnosing"
    EXPOSING = "exposing"
    SUPPORTING = "supporting"
    GUIDED_PRACTICE = "guided_practice"
    INDEPENDENT_PRACTICE = "independent_practice"
    CHECKING = "checking"
    CONSOLIDATING = "consolidating"
    MASTERED = "mastered"
    ESCALATE = "escalate"


class MasteryEstimate(str, Enum):
    """
    Estimate of student's mastery level for an objective.
    
    - LOW: Struggling, needs more support
    - MEDIUM: Progressing, needs more practice
    - HIGH: Demonstrating strong understanding
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PaceEstimate(str, Enum):
    """
    Estimate of student's learning pace across sessions.
    
    - FAST: Learns quickly, can move through material rapidly
    - NORMAL: Average learning pace
    - SLOW: Needs more time and repetition
    - UNKNOWN: Insufficient data to estimate
    """
    FAST = "fast"
    NORMAL = "normal"
    SLOW = "slow"
    UNKNOWN = "unknown"


class EngagementEstimate(str, Enum):
    """
    Estimate of student's engagement level.
    
    - HIGH: Actively participating, attentive
    - MEDIUM: Moderately engaged
    - LOW: Disengaged, distracted
    - UNKNOWN: Insufficient data to estimate
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class AffectSignal(str, Enum):
    """
    Affective/emotional signal detected from student behavior.
    
    - FRUSTRATED: Student showing signs of frustration
    - BORED: Student appears disengaged or bored
    - CONFIDENT: Student demonstrates confidence
    - ANXIOUS: Student appears anxious or uncertain
    - NEUTRAL: No strong affective signal detected
    """
    FRUSTRATED = "frustrated"
    BORED = "bored"
    CONFIDENT = "confident"
    ANXIOUS = "anxious"
    NEUTRAL = "neutral"


class SubjectEnum(str, Enum):
    """
    Hardcoded subject classification used during ingestion (to tag extracted
    topics) and during tutor discovery (to classify a student's query).
    """
    MATH = "math"
    SCIENCE = "science"
    ARABIC = "arabic"
    ENGLISH = "english"
    ISLAMIC_STUDIES = "islamic_studies"
    SOCIAL_STUDIES = "social_studies"
    TECHNOLOGY = "technology"
    ART = "art"
    PHYSICAL_EDUCATION = "physical_education"
    OTHER = "other"

