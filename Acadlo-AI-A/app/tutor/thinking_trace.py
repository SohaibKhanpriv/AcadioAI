"""
Thinking Trace Models.

Defines the structured representation of the tutor's reasoning process
during a turn. This provides visibility into what the AI did for debugging,
teacher dashboards, and future "show reasoning" UI.
"""
from dataclasses import dataclass, field
from typing import Literal, Optional, Dict, Any, List


ThinkingStage = Literal[
    "analysis",            # StudentTurnAnalysis (US-AI-M4-D)
    "performance_update",  # Snapshot + state transition (M4-B/D)
    "planning",            # TutorPlanning (M4-E)
    "response_generation"  # LLM response generation (M4-F)
]


@dataclass
class TutorThinkingStep:
    """
    Represents a single reasoning step in the tutor turn.
    
    This captures high-level metadata about what happened at each stage
    of the thinking loop, without exposing raw prompts or sensitive data.
    
    Attributes:
        stage: The stage of the thinking loop this step belongs to
        summary: Short natural-language description of what happened
        data: Optional sanitized structured details (never raw prompts)
    """
    stage: ThinkingStage
    summary: str
    
    # Optional, sanitized details (never raw prompts or sensitive data)
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        result = {
            "stage": self.stage,
            "summary": self.summary,
        }
        
        if self.data:
            result["data"] = self.data
        
        return result


def serialize_thinking_trace(trace: List[TutorThinkingStep]) -> List[Dict[str, Any]]:
    """
    Convert a thinking trace to JSON-safe format.
    
    Args:
        trace: List of TutorThinkingStep objects
        
    Returns:
        List of dictionaries suitable for API response
    """
    return [step.to_dict() for step in trace]
