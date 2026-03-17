"""
Unit tests for turn_analysis_service module.

Tests analyze_student_turn with mocked LLM:
- Valid JSON parse
- Invalid JSON / failure fallback
- Safe enum coercion
- Locale handling
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from app.tutor.enums import AffectSignal
from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    TurnKind,
    AnswerCorrectness,
    ErrorCategory,
    ReasoningQuality
)
from app.tutor.turn_analysis_service import (
    analyze_student_turn,
    _parse_llm_response,
    _safe_enum_parse,
    _build_system_prompt,
    _extract_primary_language,
    _fallback_analysis
)


class TestSafeEnumParse:
    """Tests for _safe_enum_parse helper"""
    
    def test_exact_match(self):
        """Should parse exact enum value matches"""
        result = _safe_enum_parse(TurnKind, "answer", TurnKind.OTHER)
        assert result == TurnKind.ANSWER
    
    def test_case_insensitive_match(self):
        """Should parse case-insensitive matches"""
        result = _safe_enum_parse(TurnKind, "ANSWER", TurnKind.OTHER)
        assert result == TurnKind.ANSWER
        
        result = _safe_enum_parse(TurnKind, "Answer", TurnKind.OTHER)
        assert result == TurnKind.ANSWER
    
    def test_returns_default_on_unknown(self):
        """Should return default for unknown values"""
        result = _safe_enum_parse(TurnKind, "unknown_value", TurnKind.OTHER)
        assert result == TurnKind.OTHER
    
    def test_returns_default_on_none(self):
        """Should return default for None values"""
        result = _safe_enum_parse(TurnKind, None, TurnKind.OTHER)
        assert result == TurnKind.OTHER
    
    def test_handles_whitespace(self):
        """Should handle values with whitespace"""
        result = _safe_enum_parse(TurnKind, " answer ", TurnKind.OTHER)
        assert result == TurnKind.ANSWER
    
    def test_works_with_affect_signal(self):
        """Should work with AffectSignal enum"""
        result = _safe_enum_parse(AffectSignal, "frustrated", AffectSignal.NEUTRAL)
        assert result == AffectSignal.FRUSTRATED
        
        result = _safe_enum_parse(AffectSignal, "CONFIDENT", AffectSignal.NEUTRAL)
        assert result == AffectSignal.CONFIDENT


class TestExtractPrimaryLanguage:
    """Tests for _extract_primary_language helper"""
    
    def test_extracts_arabic(self):
        """Should extract 'ar' from Arabic locales"""
        assert _extract_primary_language("ar-JO") == "ar"
        assert _extract_primary_language("ar-SA") == "ar"
        assert _extract_primary_language("ar") == "ar"
    
    def test_extracts_english(self):
        """Should extract 'en' from English locales"""
        assert _extract_primary_language("en-US") == "en"
        assert _extract_primary_language("en-GB") == "en"
        assert _extract_primary_language("en") == "en"
    
    def test_extracts_other_languages(self):
        """Should extract primary language from other locales"""
        assert _extract_primary_language("fr-CA") == "fr"
        assert _extract_primary_language("es-MX") == "es"
        assert _extract_primary_language("de-DE") == "de"
    
    def test_handles_empty_string(self):
        """Should return 'en' for empty string"""
        assert _extract_primary_language("") == "en"
    
    def test_handles_none(self):
        """Should return 'en' for None-like values"""
        assert _extract_primary_language(None) == "en"


class TestBuildSystemPrompt:
    """Tests for _build_system_prompt"""
    
    def test_is_language_neutral(self):
        """System prompt should be language-neutral"""
        prompt_ar = _build_system_prompt("ar-JO")
        prompt_en = _build_system_prompt("en-US")
        
        # Both should mention multiple languages
        assert "Arabic, English, or others" in prompt_ar
        assert "Arabic, English, or others" in prompt_en
    
    def test_includes_locale_info(self):
        """System prompt should include locale information"""
        prompt = _build_system_prompt("ar-JO")
        assert "ar-JO" in prompt
        assert "ar" in prompt  # primary language
    
    def test_requests_json_format(self):
        """System prompt should request JSON format"""
        prompt = _build_system_prompt("en-US")
        assert "JSON" in prompt
        assert "kind" in prompt
        assert "correctness" in prompt


class TestParseLlmResponse:
    """Tests for _parse_llm_response"""
    
    def test_parses_valid_json(self):
        """Should parse valid JSON response"""
        response = json.dumps({
            "kind": "answer",
            "correctness": "correct",
            "error_category": "none",
            "affect": "confident",
            "reasoning_quality": "good",
            "notes": "Student answered correctly"
        })
        
        result = _parse_llm_response(response)
        
        assert result.kind == TurnKind.ANSWER
        assert result.correctness == AnswerCorrectness.CORRECT
        assert result.error_category == ErrorCategory.NONE
        assert result.affect == AffectSignal.CONFIDENT
        assert result.reasoning_quality == ReasoningQuality.GOOD
    
    def test_parses_json_with_extra_text(self):
        """Should extract JSON from response with extra text"""
        response = """Here is the analysis:
        {"kind": "question", "correctness": "not_applicable", "error_category": "none", "affect": "neutral"}
        That's my analysis."""
        
        result = _parse_llm_response(response)
        
        assert result.kind == TurnKind.QUESTION
        assert result.affect == AffectSignal.NEUTRAL
    
    def test_handles_missing_fields_with_defaults(self):
        """Should use defaults for missing fields"""
        response = json.dumps({
            "kind": "answer"
            # Missing other fields
        })
        
        result = _parse_llm_response(response)
        
        assert result.kind == TurnKind.ANSWER
        assert result.correctness == AnswerCorrectness.NOT_APPLICABLE  # default
        assert result.affect == AffectSignal.NEUTRAL  # default
    
    def test_handles_unknown_enum_values(self):
        """Should use safe defaults for unknown enum values"""
        response = json.dumps({
            "kind": "unknown_kind",
            "correctness": "maybe",
            "error_category": "new_category",
            "affect": "happy",
            "reasoning_quality": "excellent"
        })
        
        result = _parse_llm_response(response)
        
        # Should fall back to safe defaults
        assert result.kind == TurnKind.OTHER
        assert result.correctness == AnswerCorrectness.NOT_APPLICABLE
        assert result.error_category == ErrorCategory.OTHER
        assert result.affect == AffectSignal.NEUTRAL
        assert result.reasoning_quality == ReasoningQuality.OK
    
    def test_handles_null_reasoning_quality(self):
        """Should handle null reasoning_quality"""
        response = json.dumps({
            "kind": "question",
            "correctness": "not_applicable",
            "error_category": "none",
            "affect": "neutral",
            "reasoning_quality": None
        })
        
        result = _parse_llm_response(response)
        assert result.reasoning_quality is None
    
    def test_raises_on_no_json(self):
        """Should raise ValueError when no JSON found"""
        response = "This is not JSON at all"
        
        with pytest.raises(ValueError, match="No JSON object found"):
            _parse_llm_response(response)
    
    def test_raises_on_invalid_json(self):
        """Should raise on malformed JSON"""
        response = '{"kind": "answer", "correctness": }'
        
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_response(response)


class TestFallbackAnalysis:
    """Tests for _fallback_analysis"""
    
    def test_returns_safe_defaults(self):
        """Fallback should return safe default values"""
        result = _fallback_analysis("Some error occurred")
        
        assert result.kind == TurnKind.OTHER
        assert result.correctness == AnswerCorrectness.NOT_APPLICABLE
        assert result.error_category == ErrorCategory.OTHER
        assert result.affect == AffectSignal.NEUTRAL
    
    def test_includes_error_in_notes(self):
        """Fallback should include error message in notes"""
        error_msg = "Connection timeout"
        result = _fallback_analysis(error_msg)
        
        assert error_msg in result.notes


class TestAnalyzeStudentTurn:
    """Tests for analyze_student_turn with mocked LLM"""
    
    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        """Should return parsed analysis from LLM response"""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "kind": "answer",
            "correctness": "correct",
            "error_category": "none",
            "affect": "confident",
            "reasoning_quality": "good",
            "notes": "Great work"
        })
        
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = mock_response
        
        with patch('app.tutor.turn_analysis_service.get_llm_provider', return_value=mock_provider):
            result = await analyze_student_turn(
                tenant_id="test_tenant",
                student_message="The answer is 42",
                locale="en-US",
                expected_answer="42"
            )
        
        assert result.kind == TurnKind.ANSWER
        assert result.correctness == AnswerCorrectness.CORRECT
        assert result.affect == AffectSignal.CONFIDENT
    
    @pytest.mark.asyncio
    async def test_passes_model_hint_to_provider(self):
        """Should pass model_hint to LLM provider"""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "kind": "answer",
            "correctness": "correct",
            "error_category": "none",
            "affect": "neutral"
        })
        
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = mock_response
        
        with patch('app.tutor.turn_analysis_service.get_llm_provider', return_value=mock_provider):
            await analyze_student_turn(
                tenant_id="test_tenant",
                student_message="42",
                locale="en-US",
                model_hint="gpt-4"
            )
        
        # Verify model was passed to generate
        call_kwargs = mock_provider.generate.call_args.kwargs
        assert call_kwargs.get('model') == "gpt-4"
    
    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self):
        """Should return fallback analysis when LLM fails"""
        mock_provider = AsyncMock()
        mock_provider.generate.side_effect = Exception("API Error")
        
        with patch('app.tutor.turn_analysis_service.get_llm_provider', return_value=mock_provider):
            result = await analyze_student_turn(
                tenant_id="test_tenant",
                student_message="Hello",
                locale="en-US"
            )
        
        # Should return fallback
        assert result.kind == TurnKind.OTHER
        assert result.correctness == AnswerCorrectness.NOT_APPLICABLE
        assert "API Error" in result.notes
    
    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self):
        """Should return fallback when LLM returns invalid JSON"""
        mock_response = MagicMock()
        mock_response.content = "This is not valid JSON"
        
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = mock_response
        
        with patch('app.tutor.turn_analysis_service.get_llm_provider', return_value=mock_provider):
            result = await analyze_student_turn(
                tenant_id="test_tenant",
                student_message="Hello",
                locale="en-US"
            )
        
        # Should return fallback
        assert result.kind == TurnKind.OTHER
        assert result.affect == AffectSignal.NEUTRAL
    
    @pytest.mark.asyncio
    async def test_arabic_locale_handling(self):
        """Should handle Arabic locale properly"""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "kind": "answer",
            "correctness": "correct",
            "error_category": "none",
            "affect": "confident"
        })
        
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = mock_response
        
        with patch('app.tutor.turn_analysis_service.get_llm_provider', return_value=mock_provider):
            result = await analyze_student_turn(
                tenant_id="test_tenant",
                student_message="الجواب هو ٤٢",  # "The answer is 42" in Arabic
                locale="ar-JO"
            )
        
        # Should succeed with Arabic input
        assert result.kind == TurnKind.ANSWER
        
        # Verify locale was passed correctly
        call_args = mock_provider.generate.call_args
        messages = call_args.kwargs.get('messages') or call_args.args[0]
        system_msg = messages[0].content
        assert "ar-JO" in system_msg


class TestStudentTurnAnalysisTypes:
    """Tests for StudentTurnAnalysis dataclass"""
    
    def test_affect_is_enum_type(self):
        """affect field should be AffectSignal enum"""
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.CORRECT,
            error_category=ErrorCategory.NONE,
            affect=AffectSignal.CONFIDENT
        )
        
        assert isinstance(analysis.affect, AffectSignal)
    
    def test_default_affect_is_neutral(self):
        """Default affect should be NEUTRAL"""
        analysis = StudentTurnAnalysis(
            kind=TurnKind.OTHER,
            correctness=AnswerCorrectness.NOT_APPLICABLE,
            error_category=ErrorCategory.NONE
        )
        
        assert analysis.affect == AffectSignal.NEUTRAL
    
    def test_reasoning_quality_is_enum(self):
        """reasoning_quality should be ReasoningQuality enum when set"""
        analysis = StudentTurnAnalysis(
            kind=TurnKind.ANSWER,
            correctness=AnswerCorrectness.CORRECT,
            error_category=ErrorCategory.NONE,
            reasoning_quality=ReasoningQuality.GOOD
        )
        
        assert isinstance(analysis.reasoning_quality, ReasoningQuality)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

