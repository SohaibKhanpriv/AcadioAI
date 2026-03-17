"""
Unit tests for US-AI-M4-F: Tutor Thinking Loop & Response Generation.

Tests cover:
- TutorMessage model
- TutorThinkingStep model
- Response generation service (with mocked LLM)
- Thinking loop nodes (with mocked dependencies)
- Happy path, error handling, and fallback scenarios
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from app.tutor.enums import (
    ObjectiveTeachingState,
    AffectSignal,
    MasteryEstimate
)
from app.tutor.types import ObjectivePerformanceSnapshot, ObjectiveTeachingConfig
from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    TurnKind,
    AnswerCorrectness,
    ErrorCategory,
)
from app.tutor.action_schema import (
    TutorActionPlan,
    TutorActionKind,
    DifficultyAdjustment,
)
from app.tutor.tutor_message import TutorMessage
from app.tutor.thinking_trace import TutorThinkingStep, serialize_thinking_trace
from app.tutor.response_generation import (
    generate_tutor_response,
    _get_language_name,
    _get_fallback_message,
)
# _extract_primary_language is the canonical location in turn_analysis_service
from app.tutor.turn_analysis_service import _extract_primary_language
from app.tutor.graph_context import TutorGraphContext


# ============================================================================
# Test Fixtures / Helpers
# ============================================================================

def make_analysis(
    kind: TurnKind = TurnKind.ANSWER,
    correctness: AnswerCorrectness = AnswerCorrectness.CORRECT,
    error_category: ErrorCategory = ErrorCategory.NONE,
    affect: AffectSignal = AffectSignal.NEUTRAL,
) -> StudentTurnAnalysis:
    """Helper to create student turn analysis for tests."""
    return StudentTurnAnalysis(
        kind=kind,
        correctness=correctness,
        error_category=error_category,
        affect=affect,
    )


def make_action_plan(
    kind: TutorActionKind = TutorActionKind.ASK_QUESTION,
    intent_label: str = "test_intent",
    difficulty: DifficultyAdjustment = None,
    include_encouragement: bool = False,
) -> TutorActionPlan:
    """Helper to create action plans for tests."""
    return TutorActionPlan(
        kind=kind,
        intent_label=intent_label,
        difficulty_adjustment=difficulty,
        include_encouragement=include_encouragement,
    )


def make_snapshot(
    total: int = 0,
    correct: int = 0,
    incorrect: int = 0,
    recent_answers: list = None,
    affect: AffectSignal = None,
) -> ObjectivePerformanceSnapshot:
    """Helper to create performance snapshots for tests."""
    return ObjectivePerformanceSnapshot(
        total_attempts=total,
        correct_attempts=correct,
        incorrect_attempts=incorrect,
        recent_answers=recent_answers or [],
        recent_affect=affect,
    )


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response."""
    @dataclass
    class MockResponse:
        content: str
    
    return MockResponse


# ============================================================================
# TutorMessage Tests
# ============================================================================

class TestTutorMessage:
    """Tests for TutorMessage model."""
    
    def test_basic_creation(self):
        """TutorMessage can be created with just text."""
        message = TutorMessage(text="Hello, student!")
        assert message.text == "Hello, student!"
        assert message.debug_notes is None
        assert message.suggestions is None
        assert message.metadata is None
    
    def test_full_creation(self):
        """TutorMessage can be created with all fields."""
        message = TutorMessage(
            text="Let's solve this problem together.",
            debug_notes="Generated from ASK_QUESTION",
            suggestions=["Yes", "No", "Help me"],
            metadata={"action_kind": "ask_question"},
        )
        
        assert message.text == "Let's solve this problem together."
        assert message.debug_notes == "Generated from ASK_QUESTION"
        assert message.suggestions == ["Yes", "No", "Help me"]
        assert message.metadata["action_kind"] == "ask_question"
    
    def test_to_dict_basic(self):
        """to_dict includes only text for basic message."""
        message = TutorMessage(text="Hello!")
        d = message.to_dict()
        
        assert d == {"text": "Hello!"}
    
    def test_to_dict_full(self):
        """to_dict includes all fields when present."""
        message = TutorMessage(
            text="Good job!",
            debug_notes="Encouragement generated",
            suggestions=["Continue", "Ask question"],
            metadata={"source": "llm"},
        )
        d = message.to_dict()
        
        assert d["text"] == "Good job!"
        assert d["debug_notes"] == "Encouragement generated"
        assert d["suggestions"] == ["Continue", "Ask question"]
        assert d["metadata"] == {"source": "llm"}


# ============================================================================
# TutorThinkingStep Tests
# ============================================================================

class TestTutorThinkingStep:
    """Tests for TutorThinkingStep model."""
    
    def test_basic_creation(self):
        """TutorThinkingStep can be created with stage and summary."""
        step = TutorThinkingStep(
            stage="analysis",
            summary="Analyzed the student message."
        )
        
        assert step.stage == "analysis"
        assert step.summary == "Analyzed the student message."
        assert step.data is None
    
    def test_with_data(self):
        """TutorThinkingStep can include structured data."""
        step = TutorThinkingStep(
            stage="planning",
            summary="Planned next action.",
            data={
                "action_kind": "ASK_QUESTION",
                "intent_label": "diagnostic_question",
            },
        )
        
        assert step.data["action_kind"] == "ASK_QUESTION"
        assert step.data["intent_label"] == "diagnostic_question"
    
    def test_to_dict(self):
        """to_dict returns serializable dictionary."""
        step = TutorThinkingStep(
            stage="response_generation",
            summary="Generated response.",
            data={"length_chars": 150},
        )
        
        d = step.to_dict()
        
        assert d["stage"] == "response_generation"
        assert d["summary"] == "Generated response."
        assert d["data"]["length_chars"] == 150


class TestSerializeThinkingTrace:
    """Tests for serialize_thinking_trace utility."""
    
    def test_empty_trace(self):
        """Empty trace returns empty list."""
        result = serialize_thinking_trace([])
        assert result == []
    
    def test_serializes_all_steps(self):
        """Serializes all steps in order."""
        trace = [
            TutorThinkingStep(stage="analysis", summary="Step 1"),
            TutorThinkingStep(stage="planning", summary="Step 2"),
            TutorThinkingStep(stage="response_generation", summary="Step 3"),
        ]
        
        result = serialize_thinking_trace(trace)
        
        assert len(result) == 3
        assert result[0]["stage"] == "analysis"
        assert result[1]["stage"] == "planning"
        assert result[2]["stage"] == "response_generation"


# ============================================================================
# Language Utilities Tests
# ============================================================================

class TestLanguageUtilities:
    """Tests for language extraction and mapping utilities."""
    
    def test_extract_primary_language_arabic(self):
        """Extracts 'ar' from Arabic locales."""
        assert _extract_primary_language("ar-JO") == "ar"
        assert _extract_primary_language("ar-SA") == "ar"
        assert _extract_primary_language("ar") == "ar"
    
    def test_extract_primary_language_english(self):
        """Extracts 'en' from English locales."""
        assert _extract_primary_language("en-US") == "en"
        assert _extract_primary_language("en-GB") == "en"
        assert _extract_primary_language("en") == "en"
    
    def test_extract_primary_language_other(self):
        """Extracts primary language from other locales."""
        assert _extract_primary_language("fr-FR") == "fr"
        assert _extract_primary_language("es-ES") == "es"
        assert _extract_primary_language("de-DE") == "de"
    
    def test_extract_primary_language_empty(self):
        """Returns 'en' for empty locale."""
        assert _extract_primary_language("") == "en"
        assert _extract_primary_language(None) == "en"
    
    def test_get_language_name_known(self):
        """Gets human-readable names for known languages."""
        assert _get_language_name("ar-JO") == "Arabic"
        assert _get_language_name("en-US") == "English"
        assert _get_language_name("fr-FR") == "French"
    
    def test_get_language_name_unknown(self):
        """Returns locale code for unknown languages."""
        assert _get_language_name("xx-XX") == "xx-XX"
    
    def test_get_fallback_message_arabic(self):
        """Fallback message is in Arabic for Arabic locales."""
        message = _get_fallback_message("ar-JO")
        assert "تعذّر" in message  # Arabic phrase
    
    def test_get_fallback_message_english(self):
        """Fallback message is in English for other locales."""
        message = _get_fallback_message("en-US")
        assert "couldn't generate" in message


# ============================================================================
# Response Generation Tests (with mocked LLM)
# ============================================================================

class TestGenerateTutorResponse:
    """Tests for generate_tutor_response with mocked LLM."""
    
    @pytest.mark.asyncio
    async def test_happy_path_generates_message(self, mock_llm_response):
        """Successful LLM call generates a TutorMessage."""
        action_plan = make_action_plan(
            kind=TutorActionKind.ASK_QUESTION,
            intent_label="diagnostic_question",
        )
        
        mock_response = mock_llm_response(content="What is 2 + 2?")
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        
        with patch("app.tutor.response_generation.get_llm_provider", return_value=mock_provider):
            message = await generate_tutor_response(
                tenant_id="test-tenant",
                locale="en-US",
                action_plan=action_plan,
            )
        
        assert isinstance(message, TutorMessage)
        assert message.text == "What is 2 + 2?"
        assert "ask_question" in message.metadata.get("action_kind", "")
    
    @pytest.mark.asyncio
    async def test_arabic_locale_generates_arabic(self, mock_llm_response):
        """Arabic locale should instruct LLM to respond in Arabic."""
        action_plan = make_action_plan(kind=TutorActionKind.EXPLAIN_CONCEPT)
        
        mock_response = mock_llm_response(content="مرحباً، دعنا نفهم هذا معاً")
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        
        with patch("app.tutor.response_generation.get_llm_provider", return_value=mock_provider):
            message = await generate_tutor_response(
                tenant_id="test-tenant",
                locale="ar-JO",
                action_plan=action_plan,
            )
        
        assert message.text == "مرحباً، دعنا نفهم هذا معاً"
    
    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback(self):
        """LLM failure returns safe fallback message."""
        action_plan = make_action_plan(kind=TutorActionKind.ASK_QUESTION)
        
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(side_effect=Exception("LLM API error"))
        
        with patch("app.tutor.response_generation.get_llm_provider", return_value=mock_provider):
            message = await generate_tutor_response(
                tenant_id="test-tenant",
                locale="en-US",
                action_plan=action_plan,
            )
        
        assert isinstance(message, TutorMessage)
        assert "couldn't generate" in message.text
        assert "error" in message.debug_notes.lower()
    
    @pytest.mark.asyncio
    async def test_llm_failure_arabic_fallback(self):
        """LLM failure with Arabic locale returns Arabic fallback."""
        action_plan = make_action_plan(kind=TutorActionKind.ASK_QUESTION)
        
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(side_effect=Exception("LLM API error"))
        
        with patch("app.tutor.response_generation.get_llm_provider", return_value=mock_provider):
            message = await generate_tutor_response(
                tenant_id="test-tenant",
                locale="ar-JO",
                action_plan=action_plan,
            )
        
        assert "تعذّر" in message.text  # Arabic fallback
    
    @pytest.mark.asyncio
    async def test_with_student_analysis_context(self, mock_llm_response):
        """Student analysis context is included in generation."""
        action_plan = make_action_plan(
            kind=TutorActionKind.EXPLAIN_CONCEPT,
            intent_label="clarify_misconception",
        )
        analysis = make_analysis(
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.CONCEPTUAL,
            affect=AffectSignal.FRUSTRATED,
        )
        
        mock_response = mock_llm_response(content="Let me explain this differently...")
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        
        with patch("app.tutor.response_generation.get_llm_provider", return_value=mock_provider):
            message = await generate_tutor_response(
                tenant_id="test-tenant",
                locale="en-US",
                action_plan=action_plan,
                student_analysis=analysis,
            )
        
        assert "differently" in message.text
        # Verify the LLM was called
        assert mock_provider.generate.called
    
    @pytest.mark.asyncio
    async def test_with_encouragement_flag(self, mock_llm_response):
        """Action plan with encouragement flag generates supportive message."""
        action_plan = make_action_plan(
            kind=TutorActionKind.GIVE_HINT,
            intent_label="scaffold_step",
            include_encouragement=True,
        )
        
        mock_response = mock_llm_response(content="You're doing great! Here's a hint...")
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        
        with patch("app.tutor.response_generation.get_llm_provider", return_value=mock_provider):
            message = await generate_tutor_response(
                tenant_id="test-tenant",
                locale="en-US",
                action_plan=action_plan,
            )
        
        assert "great" in message.text.lower() or "hint" in message.text.lower()


# ============================================================================
# Thinking Loop Node Tests (with mocked dependencies)
# ============================================================================

class TestNodeAnalyzeStudentTurn:
    """Tests for node_analyze_student_turn."""
    
    @pytest.mark.asyncio
    async def test_no_student_message_returns_default_analysis(self):
        """No student message should create default analysis."""
        from app.tutor.thinking_loop_nodes import node_analyze_student_turn
        
        state = TutorGraphContext(
            tenant_id="test-tenant",
            session_id="test-session",
            lesson_id="math-101",
            student_id="student-1",
            student_message=None,  # No message
        )
        state.thinking_trace = []
        
        result = await node_analyze_student_turn(state)
        
        assert result.last_analysis is not None
        assert result.last_analysis.kind == TurnKind.OTHER
        assert result.last_analysis.correctness == AnswerCorrectness.NOT_APPLICABLE
        assert len(result.thinking_trace) == 1
        assert result.thinking_trace[0].stage == "analysis"
    
    @pytest.mark.asyncio
    async def test_with_student_message_calls_analyzer(self, mock_llm_response):
        """Student message should call analyzer and store result."""
        from app.tutor.thinking_loop_nodes import node_analyze_student_turn
        
        mock_analysis = make_analysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.CORRECT,
        )
        
        state = TutorGraphContext(
            tenant_id="test-tenant",
            session_id="test-session",
            lesson_id="math-101",
            student_id="student-1",
            student_message="4",
            current_objective_id="obj-1",
        )
        state.thinking_trace = []
        state.session = MagicMock()
        state.session.session_metadata = {"locale": "en-US"}
        
        with patch("app.tutor.thinking_loop_nodes.analyze_student_turn", 
                   return_value=mock_analysis) as mock_analyze:
            result = await node_analyze_student_turn(state)
        
        assert mock_analyze.called
        assert result.last_analysis.kind == TurnKind.ANSWER
        assert result.last_analysis.correctness == AnswerCorrectness.CORRECT
        assert len(result.thinking_trace) == 1


class TestNodePlanTutorAction:
    """Tests for node_plan_tutor_action."""
    
    @pytest.mark.asyncio
    async def test_creates_plan_from_context(self):
        """Node should create action plan from context."""
        from app.tutor.thinking_loop_nodes import node_plan_tutor_action
        
        state = TutorGraphContext(
            tenant_id="test-tenant",
            session_id="test-session",
            lesson_id="math-101",
            student_id="student-1",
            current_objective_id="obj-1",
        )
        state.thinking_trace = []
        state.last_analysis = make_analysis(correctness=AnswerCorrectness.CORRECT)
        state.current_performance_snapshot = make_snapshot(
            total=3, correct=2, incorrect=1
        )
        state.objectives = {
            "obj-1": MagicMock(state=ObjectiveTeachingState.GUIDED_PRACTICE.value)
        }
        state.objective_config = ObjectiveTeachingConfig(objective_id="obj-1")
        
        result = await node_plan_tutor_action(state)
        
        assert result.tutor_action_plan is not None
        assert isinstance(result.tutor_action_plan, TutorActionPlan)
        assert len(result.thinking_trace) == 1
        assert result.thinking_trace[0].stage == "planning"
    
    @pytest.mark.asyncio
    async def test_no_objective_uses_default_plan(self):
        """No current objective should use default plan."""
        from app.tutor.thinking_loop_nodes import node_plan_tutor_action
        
        state = TutorGraphContext(
            tenant_id="test-tenant",
            session_id="test-session",
            lesson_id="math-101",
            student_id="student-1",
            current_objective_id=None,  # No objective
        )
        state.thinking_trace = []
        
        result = await node_plan_tutor_action(state)
        
        assert result.tutor_action_plan is not None
        # Default plan should be ASK_QUESTION for starting
        assert result.tutor_action_plan.kind == TutorActionKind.ASK_QUESTION


class TestNodeGenerateTutorResponse:
    """Tests for node_generate_tutor_response."""
    
    @pytest.mark.asyncio
    async def test_generates_response_from_plan(self, mock_llm_response):
        """Node should generate response from action plan."""
        from app.tutor.thinking_loop_nodes import node_generate_tutor_response
        
        state = TutorGraphContext(
            tenant_id="test-tenant",
            session_id="test-session",
            lesson_id="math-101",
            student_id="student-1",
            current_objective_id="obj-1",
        )
        state.thinking_trace = []
        state.tutor_action_plan = make_action_plan(
            kind=TutorActionKind.ASK_QUESTION,
            intent_label="diagnostic_question",
        )
        state.last_analysis = make_analysis()
        state.session = MagicMock()
        state.session.session_metadata = {"locale": "en-US"}
        
        mock_response = mock_llm_response(content="What is 3 + 5?")
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        
        with patch("app.tutor.response_generation.get_llm_provider", return_value=mock_provider):
            result = await node_generate_tutor_response(state)
        
        assert result.tutor_message is not None
        assert result.tutor_reply == "What is 3 + 5?"
        assert len(result.thinking_trace) == 1
        assert result.thinking_trace[0].stage == "response_generation"


# ============================================================================
# Integration-Style Tests (End-to-End Turn Flow)
# ============================================================================

class TestThinkingLoopFlow:
    """Integration-style tests for complete thinking loop flow."""
    
    @pytest.mark.asyncio
    async def test_happy_path_correct_answer(self, mock_llm_response):
        """Happy path: correct answer leads to follow-up question."""
        from app.tutor.thinking_loop_nodes import (
            node_analyze_student_turn,
            node_plan_tutor_action,
            node_generate_tutor_response,
        )
        
        # Create state simulating a correct answer turn
        state = TutorGraphContext(
            tenant_id="test-tenant",
            session_id="test-session",
            lesson_id="math-101",
            student_id="student-1",
            student_message="4",
            current_objective_id="obj-1",
        )
        state.thinking_trace = []
        state.session = MagicMock()
        state.session.session_metadata = {"locale": "en-US"}
        state.objectives = {
            "obj-1": MagicMock(
                state=ObjectiveTeachingState.GUIDED_PRACTICE.value,
                questions_asked=2,
                questions_correct=2,
                questions_incorrect=0,
                extra={"recent_answers": [], "recent_affect": None}
            )
        }
        state.objective_config = ObjectiveTeachingConfig(objective_id="obj-1")
        
        # Mock analysis (correct answer)
        mock_analysis = make_analysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.CORRECT,
            affect=AffectSignal.CONFIDENT,
        )
        
        mock_response = mock_llm_response(content="Great work! Now try this: What is 5 + 3?")
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        
        # Run analysis node
        with patch("app.tutor.thinking_loop_nodes.analyze_student_turn",
                   return_value=mock_analysis):
            state = await node_analyze_student_turn(state)
        
        # Simulate performance update (simplified)
        state.current_performance_snapshot = make_snapshot(
            total=3, correct=3, incorrect=0,
            recent_answers=[{"correct": True}] * 3,
            affect=AffectSignal.CONFIDENT,
        )
        
        # Run planning node
        state = await node_plan_tutor_action(state)
        
        # Run response node
        with patch("app.tutor.response_generation.get_llm_provider", return_value=mock_provider):
            state = await node_generate_tutor_response(state)
        
        # Verify full trace
        assert len(state.thinking_trace) == 3
        stages = [step.stage for step in state.thinking_trace]
        assert "analysis" in stages
        assert "planning" in stages
        assert "response_generation" in stages
        
        # Verify final response
        assert state.tutor_reply is not None
        assert "5 + 3" in state.tutor_reply
    
    @pytest.mark.asyncio
    async def test_incorrect_answer_gets_explanation(self, mock_llm_response):
        """Incorrect answer with conceptual error should get explanation."""
        from app.tutor.thinking_loop_nodes import (
            node_analyze_student_turn,
            node_plan_tutor_action,
            node_generate_tutor_response,
        )
        
        state = TutorGraphContext(
            tenant_id="test-tenant",
            session_id="test-session",
            lesson_id="math-101",
            student_id="student-1",
            student_message="7",  # Wrong answer
            current_objective_id="obj-1",
        )
        state.thinking_trace = []
        state.session = MagicMock()
        state.session.session_metadata = {"locale": "en-US"}
        state.objectives = {
            "obj-1": MagicMock(
                state=ObjectiveTeachingState.GUIDED_PRACTICE.value,
                questions_asked=2,
                questions_correct=0,
                questions_incorrect=2,
                extra={"recent_answers": [], "recent_affect": None}
            )
        }
        state.objective_config = ObjectiveTeachingConfig(objective_id="obj-1")
        
        # Mock analysis (incorrect with conceptual error)
        mock_analysis = make_analysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.INCORRECT,
            error_category=ErrorCategory.CONCEPTUAL,
            affect=AffectSignal.FRUSTRATED,
        )
        
        mock_response = mock_llm_response(content="Let me explain this differently. When we add...")
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        
        # Run analysis node
        with patch("app.tutor.thinking_loop_nodes.analyze_student_turn",
                   return_value=mock_analysis):
            state = await node_analyze_student_turn(state)
        
        # Simulate performance update
        state.current_performance_snapshot = make_snapshot(
            total=3, correct=0, incorrect=3,
            recent_answers=[{"correct": False}] * 3,
            affect=AffectSignal.FRUSTRATED,
        )
        
        # Run planning node
        state = await node_plan_tutor_action(state)
        
        # Verify plan addresses misconception
        assert state.tutor_action_plan.kind in [
            TutorActionKind.BREAKDOWN_STEP,
            TutorActionKind.EXPLAIN_CONCEPT,
        ]
        # Should include encouragement due to frustration
        assert state.tutor_action_plan.include_encouragement is True
        
        # Run response node
        with patch("app.tutor.response_generation.get_llm_provider", return_value=mock_provider):
            state = await node_generate_tutor_response(state)
        
        # Verify response is explanatory
        assert "explain" in state.tutor_reply.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
