"""
Types for Student Turn Analysis.

This module defines the models used to analyze and classify student responses
in the tutoring engine.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.tutor.enums import AffectSignal


class StudentBehavior(str, Enum):
    """Student behavior when answering: focused attempt vs guessing vs confused."""
    FOCUSED = "focused"      # On-task, genuine attempt
    GUESSING = "guessing"    # Random or implausible answers (e.g. 9999, 100)
    CONFUSED = "confused"    # Trying but clearly mixed up


class TurnKind(str, Enum):
    """Classification of what the student is trying to do in their turn"""
    ANSWER = "answer"              # Student is answering a tutor question
    REQUEST = "request"            # Student is requesting help: "explain this", "show me an example"
    QUESTION = "question"          # Student is asking a clarifying question
    META = "meta"                  # Talk about the process: "I'm tired", "this is hard"
    OFF_TOPIC = "off_topic"        # Irrelevant content
    SMALL_TALK = "small_talk"      # Non-task small talk
    OTHER = "other"


class AnswerCorrectness(str, Enum):
    """Correctness classification for answer turns"""
    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT = "incorrect"
    NOT_APPLICABLE = "not_applicable"   # e.g. when the turn is not an answer


class ErrorCategory(str, Enum):
    """Category of error when student answer is incorrect"""
    NONE = "none"                     # No error
    MISREADING = "misreading"         # Misread / miscopied numbers/text
    PROCEDURE = "procedure"           # Wrong procedure or missing step
    CONCEPTUAL = "conceptual"         # Misunderstood concept / definition
    CARELESS = "careless"             # Simple slip (sign, digit, etc.)
    LANGUAGE = "language"             # Language/wording related
    OTHER = "other"


class ReasoningQuality(str, Enum):
    """Quality of the student's reasoning in their response"""
    GOOD = "good"      # Shows clear understanding and logical steps
    OK = "ok"          # Adequate reasoning, some gaps
    WEAK = "weak"      # Poor reasoning or no explanation


class ConfidenceLevel(str, Enum):
    """Estimated confidence level in student's response."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class HelpPreference(str, Enum):
    """Preferred tutoring support mode when student seems stuck."""
    SIMPLE_EXPLANATION = "simple_explanation"
    ONE_EXAMPLE = "one_example"
    STEP_BY_STEP = "step_by_step"
    UNKNOWN = "unknown"


class RequestType(str, Enum):
    """What the student is requesting when kind=REQUEST."""
    EXPLAIN = "explain"             # "explain this", "what does that mean?"
    EXAMPLE = "example"             # "show me an example", "can you give an example?"
    STEP_BY_STEP = "step_by_step"   # "break it down", "show me step by step"
    REPEAT = "repeat"               # "say that again", "repeat the question"
    UNKNOWN = "unknown"             # Generic request for help


@dataclass
class StudentTurnAnalysis:
    """
    Structured analysis of a student's turn in the tutoring conversation.

    This is the output of the turn analysis service, capturing:
    - What kind of turn it is (answer, question, request, meta-comment, etc.)
    - If it's an answer, whether it's correct and what error type if wrong
    - If it's a request, what type of help they want
    - Affective/emotional signals
    - Confidence scores from the classifier
    """
    # How to interpret this turn in the teaching flow
    kind: TurnKind

    # Answer-specific properties (only meaningful when kind == ANSWER)
    correctness: AnswerCorrectness
    error_category: ErrorCategory
    expected_answer: Optional[str] = None
    student_answer: Optional[str] = None
    reasoning_quality: Optional[ReasoningQuality] = None

    # Request-specific (only meaningful when kind == REQUEST)
    request_type: Optional[RequestType] = None

    # Confidence signals (from classifier/LLM)
    model_confidence: Optional[float] = None  # 0-1
    confidence_level: Optional[ConfidenceLevel] = None
    low_confidence: bool = False
    low_confidence_reason: Optional[str] = None
    help_preference: Optional[HelpPreference] = None

    # Behavior: focused / guessing / confused (for MCQ and support decisions)
    behavior: StudentBehavior = field(default=StudentBehavior.FOCUSED)
    likely_guessing: bool = False  # True when answer looks random/implausible (e.g. 9999, 100)

    # Affect estimation (using enum)
    affect: AffectSignal = field(default=AffectSignal.NEUTRAL)

    # Free-form notes for logging/debugging (never shown directly to student)
    notes: Optional[str] = None
