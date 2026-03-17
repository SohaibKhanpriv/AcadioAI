"""
Tutor Message Model.

Defines the structured representation of the tutor's generated response.
This is the output of the response generation layer.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class TutorMessage:
    """
    Structured tutor message for the student.
    
    This is the output of the response generation layer:
    - The main student-facing text (already localized)
    - Optional metadata for debugging/logging
    - Optional suggestions for quick replies (future UI use)
    
    Attributes:
        text: Main student-facing text (already localized: Arabic or English)
        debug_notes: Optional short system/introspection info for logging
        suggestions: Optional list of quick replies for UI
        metadata: Optional structured extras for future use
    """
    # Main student-facing text (already localized: Arabic or English)
    text: str
    
    # Optional short "system/introspection" info for logging, not shown to student
    debug_notes: Optional[str] = None
    
    # Optional structured extras (future use for UI)
    suggestions: Optional[List[str]] = None
    
    # Generic metadata bag for extensibility
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        result = {
            "text": self.text,
        }
        
        if self.debug_notes:
            result["debug_notes"] = self.debug_notes
        
        if self.suggestions:
            result["suggestions"] = self.suggestions
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        return result
