"""Custom exceptions for the application"""


class AcadloAIException(Exception):
    """Base exception for Acadlo AI Core"""
    def __init__(self, error_code: str, message: str, details: dict = None):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(AcadloAIException):
    """Validation error exception"""
    def __init__(self, message: str, details: dict = None):
        super().__init__("VALIDATION_ERROR", message, details)


class NotFoundError(AcadloAIException):
    """Resource not found exception"""
    def __init__(self, message: str, details: dict = None):
        super().__init__("NOT_FOUND", message, details)


class InternalServerError(AcadloAIException):
    """Internal server error exception"""
    def __init__(self, message: str, details: dict = None):
        super().__init__("INTERNAL_SERVER_ERROR", message, details)

