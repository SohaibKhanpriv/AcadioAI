"""
Custom exceptions for the Tutor Runtime Engine.

Domain-specific exceptions that can be mapped to proper HTTP responses.
"""


class TutorRuntimeError(Exception):
    """Base exception for tutor runtime errors"""
    pass


class MissingContextError(TutorRuntimeError):
    """Raised when required context is missing from the graph state"""
    
    def __init__(self, field_name: str, message: str = None):
        self.field_name = field_name
        self.message = message or f"Required field '{field_name}' is missing from context"
        super().__init__(self.message)


class TurnAnalysisError(TutorRuntimeError):
    """Raised when turn analysis fails"""
    
    def __init__(self, message: str, original_error: Exception = None):
        self.original_error = original_error
        super().__init__(message)


class ObjectiveStateNotFoundError(TutorRuntimeError):
    """Raised when an ObjectiveState cannot be found"""
    
    def __init__(self, tenant_id: str, session_id: str, objective_id: str):
        self.tenant_id = tenant_id
        self.session_id = session_id
        self.objective_id = objective_id
        super().__init__(
            f"ObjectiveState not found: tenant={tenant_id}, "
            f"session={session_id}, objective={objective_id}"
        )

