"""
Student Turn Analysis Service.

This module provides LLM-based analysis of student turns using the existing
LLM abstraction (provider-agnostic).
"""
import json
import logging
from typing import Optional, TypeVar, Type

from app.providers.llm import get_llm_provider, LLMMessage
from app.core.config import settings
from app.tutor.enums import AffectSignal
from app.tutor.turn_analysis_types import (
    StudentTurnAnalysis,
    StudentBehavior,
    TurnKind,
    AnswerCorrectness,
    ErrorCategory,
    ReasoningQuality,
    ConfidenceLevel,
    HelpPreference,
    RequestType,
)

logger = logging.getLogger(__name__)

E = TypeVar('E', bound=str)


def _safe_enum_parse(
    enum_class: Type[E],
    value: Optional[str],
    default: E
) -> E:
    """
    Safely parse a string value into an enum with fallback to default.
    
    Tries exact match first, then case-insensitive, then returns default.
    Logs a warning if falling back.
    """
    if value is None:
        return default
    
    # Try exact match first
    try:
        return enum_class(value)
    except ValueError:
        pass
    
    # Try case-insensitive match
    value_lower = value.lower().strip()
    for member in enum_class:
        if member.value.lower() == value_lower:
            return member
    
    # Log warning and return default
    logger.warning(
        f"Unknown enum value '{value}' for {enum_class.__name__}, "
        f"falling back to {default.value}"
    )
    return default


def _extract_primary_language(locale: str) -> str:
    """
    Extract the primary language from a BCP-47 locale code.
    """
    if not locale:
        return "en"
    parts = locale.split('-')
    return parts[0].lower() if parts else "en"


async def analyze_student_turn(
    *,
    tenant_id: str,
    student_message: str,
    locale: str,
    expected_answer: Optional[str] = None,
    tutor_last_message: Optional[str] = None,
    objective_id: Optional[str] = None,
    objective_title: Optional[str] = None,
    lesson_id: Optional[str] = None,
    model_hint: Optional[str] = None,
    chat_history: Optional[list] = None,
) -> StudentTurnAnalysis:
    """
    Use the configured LLM provider to classify the student's turn into a StudentTurnAnalysis.
    """
    try:
        system_prompt = _build_system_prompt(locale)
        user_prompt = _build_user_prompt(
            student_message=student_message,
            expected_answer=expected_answer,
            tutor_last_message=tutor_last_message,
            objective_id=objective_id,
            objective_title=objective_title,
            lesson_id=lesson_id,
            locale=locale,
            chat_history=chat_history
        )
        
        logger.info(f"[DEBUG] analyze_student_turn called:")
        logger.info(f"[DEBUG]   student_message: {student_message}")
        logger.info(f"[DEBUG]   tutor_last_message: {tutor_last_message[:100] if tutor_last_message else 'NONE'}...")
        logger.info(f"[DEBUG]   expected_answer: {expected_answer}")
        
        llm_provider = get_llm_provider()
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]
        
        response = await llm_provider.generate(
            messages=messages,
            model=model_hint or settings.TUTOR_LLM_MODEL,
            temperature=0.3,
            tenant_id=tenant_id
        )
        
        logger.info(f"[DEBUG] LLM raw response: {response.content}")
        
        analysis = _parse_llm_response(response.content)
        
        logger.info(
            f"Analyzed student turn: tenant={tenant_id}, kind={analysis.kind.value}, "
            f"correctness={analysis.correctness.value}, affect={analysis.affect.value}"
        )
        
        return analysis
        
    except Exception as e:
        logger.error(f"Failed to analyze student turn: {str(e)}", exc_info=True)
        return _fallback_analysis(str(e))


def _build_system_prompt(locale: str) -> str:
    """
    Build the system prompt for the turn analysis LLM.
    """
    primary_lang = _extract_primary_language(locale)
    
    return f"""You are a student turn analyzer for an intelligent tutoring system.

Your job is to analyze a student's message and classify it into a structured format.

The student may respond in their native language (Arabic, English, or others). The current locale is "{locale}" (primary language: {primary_lang}). You must understand and classify their message appropriately regardless of language.

You MUST respond with ONLY a valid JSON object (no extra text) with these exact fields:
{{
  "thought_process": "Step-by-step reasoning about the student's message. For math: show your calculation here (e.g. '9+6=15, student said 15, correct').",
  "expected_answer": "The correct answer you computed from the tutor's question, or null if not a factual/math question",
  "kind": "answer" | "request" | "question" | "meta" | "off_topic" | "small_talk" | "other",
  "request_type": "explain" | "example" | "step_by_step" | "repeat" | "unknown" | null,
  "correctness": "correct" | "partially_correct" | "incorrect" | "not_applicable",
  "error_category": "none" | "misreading" | "procedure" | "conceptual" | "careless" | "language" | "other",
  "affect": "frustrated" | "bored" | "confident" | "anxious" | "neutral",
  "reasoning_quality": "good" | "ok" | "weak" | null,
  "confidence_level": "high" | "medium" | "low" | null,
  "low_confidence": true | false,
  "low_confidence_reason": "brief reason" | null,
  "help_preference": "simple_explanation" | "one_example" | "step_by_step" | "unknown" | null,
  "behavior": "focused" | "guessing" | "confused",
  "likely_guessing": true | false,
  "notes": "brief explanation for logging" | null
}}

Set "behavior" and "likely_guessing" for kind="answer" turns:
- behavior="guessing" or likely_guessing=true: student gave a random/implausible answer (e.g. 9999, 100, "banana" for a math answer, obviously wrong number).
- behavior="confused": student is trying but clearly mixed up.
- behavior="focused": genuine attempt, even if incorrect.

## CLASSIFICATION RULES (in STRICT priority order):

### 1. kind="off_topic" (CHECK THIS FIRST)
If the student's message has NOTHING to do with the lesson, school, or learning:
- "شو رح تتغذى اليوم؟" (What are you eating today?) → off_topic
- "شو اسمك؟" / "What's your name?" → off_topic  
- Talking about games, sports, weather, personal life → off_topic
- Random unrelated questions → off_topic
Set correctness="not_applicable", error_category="none".

### 2. kind="small_talk"
Friendly but non-lesson chat:
- "مرحبا" / "Hi" / greetings → small_talk
- "كيفك؟" / "How are you?" → small_talk
- "شكراً" / "Thanks" (when not responding to a question) → small_talk
Set correctness="not_applicable", error_category="none".

### 3. kind="request" (HIGH PRIORITY — check carefully)
The student is asking the tutor to DO something or expressing that they don't understand.
These are ACTION REQUESTS — the student wants help, not giving an answer.

Arabic examples (VERY IMPORTANT — memorize these patterns):
- "وضحلي" / "وضّح" → request, explain
- "اشرحلي" / "اشرح" → request, explain  
- "مش فاهم" / "مش فاهمة" → request, explain
- "ما فهمت" / "مو فاهم" → request, explain
- "شو يعني؟" / "شو القصد؟" → request, explain
- "اعطيني مثال" / "عطني مثال" → request, example
- "مثلاً؟" → request, example
- "خطوة بخطوة" / "فصّلها" → request, step_by_step
- "أعد" / "كرر" / "قولها مرة ثانية" → request, repeat
- "ساعدني" / "مش عارف شو أسوي" → request, unknown
- "ممكن توضح أكثر؟" → request, explain
- "كيف؟" (when asking how to do something) → request, explain

English examples:
- "Can you explain?" / "Explain that" → request, explain
- "I don't understand" / "I don't get it" → request, explain
- "Show me an example" → request, example
- "Break it down" / "Step by step" → request, step_by_step
- "Say that again" / "Repeat" → request, repeat
- "Help" / "I need help" → request, unknown
- "What do you mean?" → request, explain

IMPORTANT: If the student says "مش فاهم" or "I don't understand" — this is ALWAYS kind="request", request_type="explain". It is NOT an answer.

Set correctness="not_applicable", error_category="none" for all requests.

### 4. kind="answer"
The student is RESPONDING to a tutor question with actual content:
- Direct answers to questions → evaluate correctness
- Numerical answers, math solutions → evaluate correctness
- Attempts to solve or explain something → evaluate correctness
- If the tutor asked a question and the student gives a relevant attempt, it's kind="answer"

### 5. kind="question"
The student is asking a NEW knowledge question (not requesting help):
- "ليش الجاذبية بتشتغل هيك؟" → question
- "What's the formula for area?" → question
- These seek NEW information, not tutor action.

### 6. kind="meta"
ONLY for UNPROMPTED comments about emotional state or the learning process:
- "تعبت" / "I'm tired" (NOT responding to a question)
- "هاد صعب" / "This is hard" → meta
- DO NOT classify responses to questions as meta.

## MATHEMATICAL / FACTUAL CORRECTNESS (CRITICAL):
When the tutor asked a math question (e.g. "What is 9 plus 6?"), you MUST:
1. Compute the correct answer yourself FIRST (e.g. 9 + 6 = 15).
2. Compare the student's answer to YOUR computed result.
3. If the student's answer matches, set correctness="correct" — EVEN IF the student phrases it oddly.
4. Do NOT guess or approximate. Do the actual arithmetic step-by-step.
5. If the tutor's question is ambiguous or you cannot determine the expected answer, set correctness="not_applicable".

Common mistake to AVOID: marking a correct numerical answer as "incorrect" because you miscalculated. Double-check your arithmetic.

## Low-confidence detection:
- Set "low_confidence": true for: "ما بعرف", "مش عارف", "لا أعرف", "I don't know", "idk", "not sure"
- Short refusals: "no", "لا", "nope" when not answering the question  
- For non-attempt uncertainty, set kind="answer", correctness="not_applicable"
"""


def _build_user_prompt(
    student_message: str,
    expected_answer: Optional[str],
    tutor_last_message: Optional[str],
    objective_id: Optional[str],
    objective_title: Optional[str],
    lesson_id: Optional[str],
    locale: str,
    chat_history: Optional[list] = None,
) -> str:
    """Build the user prompt with context"""
    parts = []
    
    if lesson_id:
        parts.append(f"Lesson: {lesson_id}")
    if objective_title:
        parts.append(f"Current topic being taught: {objective_title}")
    elif objective_id:
        parts.append(f"Objective: {objective_id}")
    parts.append(f"Locale: {locale}")
    parts.append("")

    if chat_history:
        parts.append("Recent conversation (most recent last):")
        for item in chat_history[-6:]:
            role = item.get("role", "unknown")
            content = item.get("content", "")
            content = content[:200].replace("\n", " ").strip()
            parts.append(f"- {role}: {content}")
        parts.append("")
    
    if tutor_last_message:
        parts.append(f"Tutor's question/message: {tutor_last_message}")
        parts.append("")
    
    parts.append(f"Student's response: {student_message}")
    parts.append("")
    
    if expected_answer:
        parts.append(f"Expected answer: {expected_answer}")
        parts.append("(Evaluate the student's response against this expected answer)")
    elif tutor_last_message:
        parts.append("(Evaluate the student's response in context of the tutor's message above)")
    else:
        parts.append("(No question context provided - classify the turn kind)")
    
    parts.append("")
    parts.append("Return ONLY the JSON object, no extra text.")
    
    return "\n".join(parts)


def _parse_llm_response(response_text: str) -> StudentTurnAnalysis:
    """
    Parse LLM JSON response into StudentTurnAnalysis.
    """
    try:
        response_text = response_text.strip()
        
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            logger.warning(
                f"No JSON object found in LLM response (length: {len(response_text)} chars)"
            )
            raise ValueError("No JSON object found in response")
        
        json_str = response_text[start_idx:end_idx + 1]
        data = json.loads(json_str)
        
        # Parse enums with safe fallbacks
        kind = _safe_enum_parse(TurnKind, data.get("kind"), TurnKind.OTHER)
        correctness = _safe_enum_parse(
            AnswerCorrectness, data.get("correctness"), AnswerCorrectness.NOT_APPLICABLE
        )
        error_category = _safe_enum_parse(
            ErrorCategory, data.get("error_category"), ErrorCategory.OTHER
        )
        affect = _safe_enum_parse(AffectSignal, data.get("affect"), AffectSignal.NEUTRAL)
        
        reasoning_quality = None
        raw_rq = data.get("reasoning_quality")
        if raw_rq is not None:
            reasoning_quality = _safe_enum_parse(
                ReasoningQuality, raw_rq, ReasoningQuality.OK
            )

        confidence_level = None
        raw_cl = data.get("confidence_level")
        if raw_cl is not None:
            confidence_level = _safe_enum_parse(
                ConfidenceLevel, raw_cl, ConfidenceLevel.MEDIUM
            )

        help_preference = None
        raw_hp = data.get("help_preference")
        if raw_hp is not None:
            help_preference = _safe_enum_parse(
                HelpPreference, raw_hp, HelpPreference.UNKNOWN
            )

        # Parse request_type (only meaningful when kind=REQUEST)
        request_type = None
        raw_rt = data.get("request_type")
        if raw_rt is not None:
            request_type = _safe_enum_parse(
                RequestType, raw_rt, RequestType.UNKNOWN
            )

        behavior = _safe_enum_parse(StudentBehavior, data.get("behavior"), StudentBehavior.FOCUSED)
        likely_guessing = bool(data.get("likely_guessing", False))
        
        return StudentTurnAnalysis(
            kind=kind,
            correctness=correctness,
            error_category=error_category,
            reasoning_quality=reasoning_quality,
            affect=affect,
            confidence_level=confidence_level,
            low_confidence=bool(data.get("low_confidence", False)),
            low_confidence_reason=data.get("low_confidence_reason"),
            help_preference=help_preference,
            request_type=request_type,
            behavior=behavior,
            likely_guessing=likely_guessing,
            notes=data.get("notes"),
            model_confidence=None,
        )
        
    except json.JSONDecodeError as e:
        logger.warning(
            f"JSON parse error in LLM response: {str(e)}, "
            f"response_length={len(response_text)} chars"
        )
        raise
    except Exception as e:
        logger.warning(
            f"Failed to parse LLM response: {type(e).__name__}: {str(e)}"
        )
        raise


def _fallback_analysis(error_message: str) -> StudentTurnAnalysis:
    """Return safe fallback analysis when LLM fails"""
    return StudentTurnAnalysis(
        kind=TurnKind.OTHER,
        correctness=AnswerCorrectness.NOT_APPLICABLE,
        error_category=ErrorCategory.OTHER,
        affect=AffectSignal.NEUTRAL,
        confidence_level=ConfidenceLevel.MEDIUM,
        low_confidence=False,
        help_preference=HelpPreference.UNKNOWN,
        behavior=StudentBehavior.FOCUSED,
        likely_guessing=False,
        notes=f"Fallback analysis due to LLM error: {error_message}"
    )
