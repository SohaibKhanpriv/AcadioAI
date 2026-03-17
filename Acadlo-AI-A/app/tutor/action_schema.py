"""
Tutor Action Schema.

Defines the structured representation of what the tutor should do next.
This is the output of the planning layer and input to response generation.

The schema is:
- Small but expressive enough to cover basic teaching actions
- Serializable (JSON friendly)
- Independent from any specific UI (web, mobile, voice)
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any


class TutorActionKind(str, Enum):
    """
    The type of action the tutor should take next.
    
    Each action kind represents a pedagogical intent, not final wording.
    """
    # Question-based actions
    ASK_QUESTION = "ask_question"           # Ask student a question
    ASK_MCQ = "ask_mcq"                     # Present A/B/C/D only, reject invalid input (guessing mode)
    CHECK_UNDERSTANDING = "check_understanding"  # Quick check / mastery probe
    
    # Explanation-based actions
    EXPLAIN_CONCEPT = "explain_concept"     # Explain or re-explain a concept
    BREAKDOWN_STEP = "breakdown_step"       # Break down into smaller steps
    GIVE_HINT = "give_hint"                 # Provide a hint without full answer
    
    # Support actions
    ENCOURAGE = "encourage"                 # Motivational / emotional support
    META_COACHING = "meta_coaching"         # Talk about learning strategy, not content
    ADJUST_DIFFICULTY = "adjust_difficulty" # Signal to adjust task difficulty
    
    # Flow control actions
    SWITCH_OBJECTIVE = "switch_objective"   # Move to a different objective
    ESCALATE = "escalate"                   # Requires human intervention
    END_LESSON = "end_lesson"               # Complete the lesson


class DifficultyAdjustment(str, Enum):
    """Direction of difficulty adjustment for the next task."""
    EASIER = "easier"
    SAME = "same"
    HARDER = "harder"


@dataclass
class TutorActionPlan:
    """
    Structured plan for the tutor's next action.
    
    This is the output of the planning layer. It captures WHAT the tutor
    should do, not HOW to say it (that's response generation).
    
    Attributes:
        kind: The type of action to take
        target_objective_id: Which objective this action targets (optional)
        difficulty_adjustment: Whether to make task easier/same/harder
        intent_label: High-level intent for response generator
        include_encouragement: Whether to add encouragement to the action
        escalation_reason: Reason for escalation (when kind=ESCALATE)
        metadata: Generic extensibility bag
    """
    kind: TutorActionKind
    
    # Target objective (for SWITCH_OBJECTIVE or multi-objective scenarios)
    target_objective_id: Optional[str] = None
    
    # Difficulty adjustment hint
    difficulty_adjustment: Optional[DifficultyAdjustment] = None
    
    # High-level intent label used by response generator
    # Examples: "diagnostic_question", "scaffold_example", "mastery_check",
    #           "clarify_misconception", "summary_and_links", "normalize_struggle"
    intent_label: Optional[str] = None
    
    # Whether to combine this action with encouragement
    # (Alternative to separate ENCOURAGE action)
    include_encouragement: bool = False
    
    # Escalation reason (only meaningful when kind=ESCALATE)
    escalation_reason: Optional[str] = None
    
    # Generic metadata bag for future extensibility
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        result = {
            "kind": self.kind.value,
            "target_objective_id": self.target_objective_id,
            "intent_label": self.intent_label,
            "include_encouragement": self.include_encouragement,
        }
        
        if self.difficulty_adjustment:
            result["difficulty_adjustment"] = self.difficulty_adjustment.value
        
        if self.escalation_reason:
            result["escalation_reason"] = self.escalation_reason
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        return result

