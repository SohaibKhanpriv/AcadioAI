"""
Unit and integration tests for US-AI-M4-G: Tutor HTTP API & Service Contracts.

Tests cover:
- StartTutorSessionRequest validation
- ContinueTutorSessionRequest validation
- /v1/tutor/start endpoint (happy path, validation errors)
- /v1/tutor/turn endpoint (happy path, session not found, tenant mismatch, terminal session)
- Thinking trace inclusion
- Error response structure
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from dataclasses import dataclass

from app.models.schemas import (
    StartTutorSessionRequest,
    ContinueTutorSessionRequest,
    TutorTurnResponse,
    TutorErrorResponse,
    TutorErrorCodes,
)


# =============================================================================
# DTO Validation Tests
# =============================================================================

class TestStartTutorSessionRequest:
    """Tests for StartTutorSessionRequest validation."""
    
    def test_valid_request(self):
        """Valid request should be created successfully."""
        request = StartTutorSessionRequest(
            tenant_id="tenant-1",
            student_id="student-1",
            lesson_id="lesson-1",
            objective_ids=["obj-1", "obj-2"],
        )
        
        assert request.tenant_id == "tenant-1"
        assert request.student_id == "student-1"
        assert request.lesson_id == "lesson-1"
        assert request.objective_ids == ["obj-1", "obj-2"]
        assert request.objectives is None
        assert request.include_thinking_trace is False  # Default
    
    def test_empty_tenant_id_rejected(self):
        """Empty tenant_id should be rejected."""
        with pytest.raises(ValueError):
            StartTutorSessionRequest(
                tenant_id="",
                student_id="student-1",
                lesson_id="lesson-1",
                objective_ids=["obj-1"],
            )
    
    def test_missing_objective_ids_and_objectives_rejected(self):
        """Request should be rejected when both objective lists are missing/empty."""
        with pytest.raises(ValueError):
            StartTutorSessionRequest(
                tenant_id="tenant-1",
                student_id="student-1",
                lesson_id="lesson-1",
                objective_ids=[],
            )

    def test_valid_with_plain_objectives_without_ids(self):
        """Plain-English objectives should be accepted when objective_ids is omitted."""
        request = StartTutorSessionRequest(
            tenant_id="tenant-1",
            student_id="student-1",
            lesson_id="lesson-1",
            objectives=["Understand fractions", "Add fractions"],
        )
        assert request.objective_ids is None
        assert request.objectives == ["Understand fractions", "Add fractions"]
    
    def test_full_request_with_all_fields(self):
        """Request with all optional fields should work."""
        request = StartTutorSessionRequest(
            tenant_id="tenant-1",
            student_id="student-1",
            lesson_id="lesson-1",
            objective_ids=["obj-1"],
            ou_id="ou-123",
            region_id="JO",
            program_id="grade1-math",
            context_scopes=["tenant", "ou:123"],
            locale="ar-JO",
            initial_student_message="Hello!",
            lesson_config={"difficulty": "easy"},
            include_thinking_trace=True,
        )
        
        assert request.ou_id == "ou-123"
        assert request.locale == "ar-JO"
        assert request.include_thinking_trace is True


class TestContinueTutorSessionRequest:
    """Tests for ContinueTutorSessionRequest validation."""
    
    def test_valid_request(self):
        """Valid request should be created successfully."""
        request = ContinueTutorSessionRequest(
            tenant_id="tenant-1",
            session_id="session-123",
            student_message="4",
        )
        
        assert request.tenant_id == "tenant-1"
        assert request.session_id == "session-123"
        assert request.student_message == "4"
    
    def test_empty_student_message_rejected(self):
        """Empty student_message should be rejected."""
        with pytest.raises(ValueError):
            ContinueTutorSessionRequest(
                tenant_id="tenant-1",
                session_id="session-123",
                student_message="",
            )


class TestTutorTurnResponse:
    """Tests for TutorTurnResponse structure."""
    
    def test_basic_response(self):
        """Basic response should have required fields."""
        response = TutorTurnResponse(
            tenant_id="tenant-1",
            session_id="session-123",
            lesson_id="lesson-1",
            current_objective_id="obj-1",
            tutor_reply="Hello! Let's learn math.",
            lesson_complete=False,
        )
        
        assert response.tenant_id == "tenant-1"
        assert response.tutor_reply == "Hello! Let's learn math."
        assert response.lesson_complete is False
        assert response.debug is None
    
    def test_response_with_debug(self):
        """Response can include debug with thinking trace."""
        response = TutorTurnResponse(
            tenant_id="tenant-1",
            session_id="session-123",
            lesson_id="lesson-1",
            current_objective_id="obj-1",
            tutor_reply="Hello!",
            lesson_complete=False,
            debug={
                "thinking_trace": [
                    {"stage": "analysis", "summary": "Analyzed message"},
                    {"stage": "planning", "summary": "Planned response"},
                ],
                "request_id": "abc123",
            },
        )
        
        assert response.debug is not None
        assert "thinking_trace" in response.debug
        assert len(response.debug["thinking_trace"]) == 2


class TestTutorErrorResponse:
    """Tests for TutorErrorResponse structure."""
    
    def test_error_response(self):
        """Error response should have code and message."""
        error = TutorErrorResponse(
            code=TutorErrorCodes.SESSION_NOT_FOUND,
            message="Session not found: session-123",
            details={"request_id": "abc123"},
        )
        
        assert error.code == "session_not_found"
        assert "Session not found" in error.message
        assert error.details["request_id"] == "abc123"


# =============================================================================
# API Endpoint Tests (with mocked dependencies)
# =============================================================================

@pytest.fixture
def mock_tutor_result():
    """Create a mock TutorTurnResult."""
    @dataclass
    class MockTutorTurnResult:
        tenant_id: str = "tenant-1"
        session_id: str = "session-123"
        lesson_id: str = "lesson-1"
        current_objective_id: str = "obj-1"
        tutor_reply: str = "Hello! What is 2 + 2?"
        lesson_complete: bool = False
        thinking_trace: list = None
    
    return MockTutorTurnResult


class TestTutorStartEndpoint:
    """Tests for POST /v1/tutor/start endpoint."""
    
    @pytest.mark.asyncio
    async def test_start_happy_path(self, mock_tutor_result):
        """Happy path: valid request returns 200 with session."""
        from app.api.v1.tutor import start_tutor_session
        from app.models.schemas import StartTutorSessionRequest
        
        request = StartTutorSessionRequest(
            tenant_id="tenant-1",
            student_id="student-1",
            lesson_id="lesson-1",
            objective_ids=["obj-1", "obj-2"],
        )
        
        mock_result = mock_tutor_result()
        mock_db = AsyncMock()
        
        with patch("app.api.v1.tutor.run_tutor_start", return_value=mock_result):
            response = await start_tutor_session(request, mock_db)
        
        assert response.tenant_id == "tenant-1"
        assert response.session_id == "session-123"
        assert response.tutor_reply == "Hello! What is 2 + 2?"
        assert response.lesson_complete is False
    
    @pytest.mark.asyncio
    async def test_start_with_thinking_trace(self, mock_tutor_result):
        """When include_thinking_trace=True, debug should contain trace."""
        from app.api.v1.tutor import start_tutor_session
        from app.models.schemas import StartTutorSessionRequest
        
        request = StartTutorSessionRequest(
            tenant_id="tenant-1",
            student_id="student-1",
            lesson_id="lesson-1",
            objective_ids=["obj-1"],
            include_thinking_trace=True,
        )
        
        mock_result = mock_tutor_result()
        mock_result.thinking_trace = [
            {"stage": "analysis", "summary": "Analyzed"},
            {"stage": "planning", "summary": "Planned"},
        ]
        mock_db = AsyncMock()
        
        with patch("app.api.v1.tutor.run_tutor_start", return_value=mock_result):
            response = await start_tutor_session(request, mock_db)
        
        assert response.debug is not None
        assert "thinking_trace" in response.debug
        assert len(response.debug["thinking_trace"]) == 2
    
    @pytest.mark.asyncio
    async def test_start_with_locale(self, mock_tutor_result):
        """Locale should be passed to runner."""
        from app.api.v1.tutor import start_tutor_session
        from app.models.schemas import StartTutorSessionRequest
        
        request = StartTutorSessionRequest(
            tenant_id="tenant-1",
            student_id="student-1",
            lesson_id="lesson-1",
            objective_ids=["obj-1"],
            locale="en-US",
        )
        
        mock_result = mock_tutor_result()
        mock_db = AsyncMock()
        
        with patch("app.api.v1.tutor.run_tutor_start", return_value=mock_result) as mock_run:
            await start_tutor_session(request, mock_db)
        
        # Verify locale was passed
        assert mock_run.called
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("locale") == "en-US"


class TestTutorTurnEndpoint:
    """Tests for POST /v1/tutor/turn endpoint."""
    
    @pytest.mark.asyncio
    async def test_turn_happy_path(self, mock_tutor_result):
        """Happy path: valid request returns 200 with tutor reply."""
        from app.api.v1.tutor import continue_tutor_session
        from app.models.schemas import ContinueTutorSessionRequest
        
        request = ContinueTutorSessionRequest(
            tenant_id="tenant-1",
            session_id="session-123",
            student_message="4",
        )
        
        mock_result = mock_tutor_result()
        mock_result.tutor_reply = "Great! 2 + 2 = 4. Excellent work!"
        mock_db = AsyncMock()
        
        with patch("app.api.v1.tutor.run_tutor_turn", return_value=mock_result):
            response = await continue_tutor_session(request, mock_db)
        
        assert response.session_id == "session-123"
        assert "Excellent work" in response.tutor_reply
    
    @pytest.mark.asyncio
    async def test_turn_session_not_found(self):
        """Session not found should return 404."""
        from fastapi import HTTPException
        from app.api.v1.tutor import continue_tutor_session
        from app.models.schemas import ContinueTutorSessionRequest
        from app.tutor.exceptions import ObjectiveStateNotFoundError
        
        request = ContinueTutorSessionRequest(
            tenant_id="tenant-1",
            session_id="nonexistent-session",
            student_message="4",
        )
        
        mock_db = AsyncMock()
        
        # ObjectiveStateNotFoundError requires tenant_id, session_id, objective_id
        with patch("app.api.v1.tutor.run_tutor_turn", side_effect=ObjectiveStateNotFoundError(
            tenant_id="tenant-1",
            session_id="nonexistent-session",
            objective_id="obj-1"
        )):
            with pytest.raises(HTTPException) as exc_info:
                await continue_tutor_session(request, mock_db)
        
        # Assertions must be OUTSIDE the pytest.raises block
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["code"] == TutorErrorCodes.SESSION_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_turn_tenant_mismatch(self):
        """Tenant mismatch should return 403."""
        from fastapi import HTTPException
        from app.api.v1.tutor import continue_tutor_session
        from app.models.schemas import ContinueTutorSessionRequest
        
        request = ContinueTutorSessionRequest(
            tenant_id="tenant-1",
            session_id="session-123",
            student_message="4",
        )
        
        mock_db = AsyncMock()
        
        with patch("app.api.v1.tutor.run_tutor_turn", side_effect=ValueError("Tenant mismatch: session belongs to different tenant")):
            with pytest.raises(HTTPException) as exc_info:
                await continue_tutor_session(request, mock_db)
        
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == TutorErrorCodes.TENANT_MISMATCH
    
    @pytest.mark.asyncio
    async def test_turn_session_terminal(self):
        """Terminal session should return 409."""
        from fastapi import HTTPException
        from app.api.v1.tutor import continue_tutor_session
        from app.models.schemas import ContinueTutorSessionRequest
        
        request = ContinueTutorSessionRequest(
            tenant_id="tenant-1",
            session_id="session-123",
            student_message="4",
        )
        
        mock_db = AsyncMock()
        
        with patch("app.api.v1.tutor.run_tutor_turn", side_effect=ValueError("Session is complete and cannot accept new turns")):
            with pytest.raises(HTTPException) as exc_info:
                await continue_tutor_session(request, mock_db)
        
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == TutorErrorCodes.SESSION_TERMINAL
    
    @pytest.mark.asyncio
    async def test_turn_with_thinking_trace(self, mock_tutor_result):
        """When include_thinking_trace=True, debug should contain trace."""
        from app.api.v1.tutor import continue_tutor_session
        from app.models.schemas import ContinueTutorSessionRequest
        
        request = ContinueTutorSessionRequest(
            tenant_id="tenant-1",
            session_id="session-123",
            student_message="4",
            include_thinking_trace=True,
        )
        
        mock_result = mock_tutor_result()
        mock_result.thinking_trace = [
            {"stage": "analysis", "summary": "Analyzed: correct answer"},
            {"stage": "planning", "summary": "Plan: ask next question"},
            {"stage": "response_generation", "summary": "Generated praise"},
        ]
        mock_db = AsyncMock()
        
        with patch("app.api.v1.tutor.run_tutor_turn", return_value=mock_result):
            response = await continue_tutor_session(request, mock_db)
        
        assert response.debug is not None
        assert "thinking_trace" in response.debug
        assert len(response.debug["thinking_trace"]) == 3


# =============================================================================
# Error Code Constants Tests
# =============================================================================

class TestTutorErrorCodes:
    """Tests for error code constants."""
    
    def test_error_codes_are_strings(self):
        """All error codes should be strings."""
        assert TutorErrorCodes.VALIDATION_ERROR == "validation_error"
        assert TutorErrorCodes.SESSION_NOT_FOUND == "session_not_found"
        assert TutorErrorCodes.TENANT_MISMATCH == "tenant_mismatch"
        assert TutorErrorCodes.SESSION_TERMINAL == "session_terminal"
        assert TutorErrorCodes.INTERNAL_ERROR == "internal_error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
