"""
Tutor Response Generation Service.

This module implements LLM-based response generation that takes a TutorActionPlan
and generates a natural-language tutor message consistent with that plan.

The design is:
- Provider-agnostic (uses the generic LLM abstraction)
- Multi-language aware (respects locale parameter)
- Safe (includes basic prompt-level safety guidance)
"""
import logging
import re
from typing import Optional, Dict, Any

from app.providers.llm import get_llm_provider, LLMMessage
from app.core.config import settings
from app.tutor.action_schema import TutorActionPlan, TutorActionKind, DifficultyAdjustment
from app.tutor.turn_analysis_types import StudentTurnAnalysis
from app.tutor.tutor_message import TutorMessage
# Reuse existing language extraction utility - no duplication
from app.tutor.turn_analysis_service import _extract_primary_language

logger = logging.getLogger(__name__)


# Language code to human-readable language name mapping
LANGUAGE_NAMES: Dict[str, str] = {
    "ar": "Arabic",
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "tr": "Turkish",
    "ur": "Urdu",
    "hi": "Hindi",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "it": "Italian",
    "ru": "Russian",
}


def _get_language_name(locale: str) -> str:
    """Get human-readable language name from locale."""
    primary_lang = _extract_primary_language(locale)
    return LANGUAGE_NAMES.get(primary_lang, locale)


def _get_fallback_message(locale: str) -> str:
    """Get a fallback message when LLM fails."""
    primary_lang = _extract_primary_language(locale)
    
    if primary_lang == "ar":
        return "\u062a\u0639\u0630\u0651\u0631 \u0639\u0644\u064a\u0651 \u062a\u0648\u0644\u064a\u062f \u0631\u062f \u0641\u064a \u0647\u0630\u0647 \u0627\u0644\u0644\u062d\u0638\u0629\u060c \u062c\u0631\u0651\u0628 \u0645\u0631\u0629 \u0623\u062e\u0631\u0649 \u0645\u0646 \u0641\u0636\u0644\u0643."
    else:
        return "I couldn't generate a response right now. Please try again."


async def generate_tutor_response(
    *,
    tenant_id: str,
    locale: str,
    action_plan: TutorActionPlan,
    lesson_context: Optional[Dict[str, Any]] = None,
    objective_context: Optional[Dict[str, Any]] = None,
    student_analysis: Optional[StudentTurnAnalysis] = None,
    model_hint: Optional[str] = None,
    chat_history: Optional[list] = None,
    progress_evaluation: Optional[Any] = None,
    student_message: Optional[str] = None,
    last_tutor_message: Optional[str] = None,
    grade_band: Optional[str] = None,
    skill_level: Optional[str] = None,
    rag_chunks: Optional[list] = None,
    rag_source: Optional[str] = None,
) -> TutorMessage:
    """
    Generate a tutor message from a TutorActionPlan using the configured LLM.
    """
    try:
        system_prompt = _build_system_prompt(locale, action_plan, grade_band=grade_band, skill_level=skill_level)
        user_prompt = _build_user_prompt(
            action_plan=action_plan,
            lesson_context=lesson_context,
            objective_context=objective_context,
            student_analysis=student_analysis,
            locale=locale,
            chat_history=chat_history,
            progress_evaluation=progress_evaluation,
            student_message=student_message,
            last_tutor_message=last_tutor_message,
        )

        # Inject RAG reference material when available
        if rag_chunks and rag_source == "ingested":
            rag_block_parts = ["=== REFERENCE MATERIAL (from student's textbook) ==="]
            for i, chunk in enumerate(rag_chunks[:8], start=1):
                text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
                rag_block_parts.append(f"[{i}] {text}")
            rag_block_parts.append("===")
            rag_block_parts.append(
                "Use the above reference material for your explanations, examples, "
                "and questions whenever relevant. Cite specific content rather than "
                "inventing generic examples."
            )
            user_prompt = "\n".join(rag_block_parts) + "\n\n" + user_prompt
        elif not rag_chunks:
            user_prompt += (
                "\n\n[Note: No course material is available for this topic. "
                "Use your general knowledge.]"
            )
        
        llm_provider = get_llm_provider()
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]
        
        response = await llm_provider.generate(
            messages=messages,
            model=model_hint or settings.TUTOR_LLM_MODEL,
            temperature=0.8,  # Slightly higher for more natural conversation
            tenant_id=tenant_id,
        )
        
        text = response.content.strip()
        if not text:
            logger.warning("LLM returned empty tutor response; using localized fallback")
            return TutorMessage(
                text=_get_fallback_message(locale),
                debug_notes="Fallback response due to empty model output",
                metadata={
                    "action_kind": action_plan.kind.value,
                    "intent_label": action_plan.intent_label,
                    "fallback_reason": "empty_model_output",
                },
            )
        
        # Extract [EXPECTED_ANSWER: ...] tag if present
        expected_answer = None
        ea_match = re.search(r"\[EXPECTED_ANSWER:\s*(.+?)\]", text)
        if ea_match:
            expected_answer = ea_match.group(1).strip()
            text = text[:ea_match.start()].rstrip() + text[ea_match.end():]
            text = text.strip()
        
        logger.info(
            f"Generated tutor response: tenant={tenant_id}, locale={locale}, "
            f"action={action_plan.kind.value}, length={len(text)} chars, "
            f"expected_answer={expected_answer}"
        )
        
        meta = {
            "action_kind": action_plan.kind.value,
            "intent_label": action_plan.intent_label,
        }
        if expected_answer:
            meta["expected_answer"] = expected_answer
        
        return TutorMessage(
            text=text,
            debug_notes=f"Generated from {action_plan.kind.value} action plan",
            metadata=meta,
        )
        
    except Exception as e:
        logger.error(f"Failed to generate tutor response: {str(e)}", exc_info=True)
        return TutorMessage(
            text=_get_fallback_message(locale),
            debug_notes=f"Fallback response due to error: {str(e)}",
        )


def _build_system_prompt(
    locale: str,
    action_plan: TutorActionPlan,
    grade_band: Optional[str] = None,
    skill_level: Optional[str] = None,
) -> str:
    """Build the system prompt for response generation."""
    language_name = _get_language_name(locale)
    action_guidance = _get_action_guidance(action_plan)
    grade_line = f"Use simple, age-appropriate language for grade {grade_band}." if grade_band else "Use age-appropriate language."
    level_line = f"Adjust difficulty and scaffolding to the student's level: {skill_level.title()}." if skill_level else "Adjust difficulty to the student's level."
    
    return f"""You are Acadlo — a warm, experienced private tutor. You are NOT a chatbot, NOT an AI assistant, NOT a quiz bot. You are a real teacher who genuinely cares about this student's learning.

## TEACHING LOOP (STRICT)

- **Micro-learning:** ONE idea at a time. Do NOT give full explanations upfront.
- **Strict sequence:** Introduce the concept briefly → give ONE example → student tries → you evaluate → adapt (easier/harder/different method). Do not skip to quizzing before the student has seen one clear example.
- **No full explanations upfront.** Do not dump the whole concept. Introduce, then one example, then let them try.

## YOUR PERSONALITY

- **Friendly but firm.** Encouraging, not permissive. You redirect off-topic firmly and bring the student back to the lesson. Occasional light touch is fine, but you are in charge of the lesson.
- **Patient and encouraging.** You never make the student feel stupid. You treat every wrong answer as useful data, not failure.
- **Conversational and natural.** You talk like a person sitting next to the student. Short sentences. Natural flow. You don't give speeches or lectures.
- **Adaptive.** You read the student's mood. If they're frustrated, you slow down and empathize FIRST. If they're confident, you challenge them.
- **Proactive.** You don't ask "how would you like me to help?" — you decide and act.

## GRADE AND LEVEL

{grade_line}
{level_line}

## WHAT YOU NEVER DO

1. You NEVER give a full explanation before the student has tried. One idea, one example, then they try.
2. You NEVER use generic praise every turn. If you encourage, make it specific.
3. You NEVER ask "how would you like me to help?" or present options — you decide and act.
4. You NEVER ignore what the student said. Always acknowledge their answer before moving on.
5. You NEVER use markdown, bullet points, or headers. Just talk naturally.
6. You NEVER follow the student off-topic. If they ask about something unrelated (e.g. "What is the capital of France?" during math), you firmly redirect: "Let's stay with our lesson for now — we can talk about that another time." Do NOT answer off-topic questions.

## LANGUAGE

Respond ONLY in {language_name}. This is mandatory. Every word must be in {language_name}.

## YOUR TASK THIS TURN

{action_guidance}

## EXPECTED ANSWER (CRITICAL)

When your response contains a question for the student to answer (math, factual, MCQ, etc.), you MUST end your response with a hidden tag on its own line:
[EXPECTED_ANSWER: <the correct answer>]

Examples:
- If you ask "What is 7 plus 5?", end with: [EXPECTED_ANSWER: 12]
- If you ask MCQ with answer B (4), end with: [EXPECTED_ANSWER: B) 4]
- If your message doesn't ask a question (e.g. explanation only), do NOT include this tag.

This tag is stripped before showing to the student. It helps us evaluate their next answer accurately.

## CONVERSATION STYLE

Good (English): "Hmm, close! But the question was about what you ate, not what's left. Think of it like giving away 1 sticker out of 4 — you gave away 1/4."
Bad: Generic praise + "Would you like me to explain?" (you decide, don't ask)."""


def _get_action_guidance(action_plan: TutorActionPlan) -> str:
    """Get specific guidance based on action kind and intent."""
    kind = action_plan.kind
    intent = action_plan.intent_label or ""
    
    # ----- Intent-specific overrides (highest priority) -----
    
    # Off-topic redirect — do NOT engage, redirect immediately
    if intent == "redirect_off_topic":
        guidance = (
            "The student went off-topic. Do NOT engage with their off-topic message at all. "
            "Do NOT acknowledge it, answer it, or comment on it. "
            "Simply redirect back to the lesson topic immediately. "
            "Example: 'يلّا نرجع لدرسنا...' or 'خلّينا نكمل اللي كنا فيه...'. "
            "Then continue teaching or ask the next question as if the off-topic message didn't happen."
        )

    # Answer student's question directly
    elif intent == "answer_student_question":
        guidance = (
            "The student asked a question. Answer it directly and clearly. "
            "Don't deflect. Don't ask a question back. Just answer what they asked, "
            "then naturally continue with the lesson."
        )

    # Student directly requested explanation
    elif intent == "direct_explain_on_request":
        guidance = (
            "The student asked you to explain. Do it. Explain the concept in fresh, "
            "simple words. Use a new analogy they haven't heard yet. Don't ask a question at the end."
        )
    
    # Student directly requested an example
    elif intent == "direct_example_on_request":
        guidance = (
            "The student asked for an example. Give ONE clear, concrete example "
            "using something from their daily life. Walk through it. Don't quiz them after."
        )
    
    # Student directly requested step-by-step
    elif intent == "direct_breakdown_on_request":
        guidance = (
            "The student wants step-by-step help. Break the concept into 2-3 tiny steps. "
            "Number them. Keep each step to one sentence."
        )
    
    # Student asked to repeat
    elif intent == "repeat_last_explanation":
        guidance = (
            "The student wants you to repeat or clarify. Say it again but simpler and shorter. "
            "Use different words from last time."
        )
    
    # Auto-decided: simple explanation
    elif intent in ["auto_simple_explanation", "auto_explain_conceptual_gap", "auto_explain_progress_based"]:
        guidance = (
            "Explain the concept simply, like you're explaining to a friend. Use plain everyday words. "
            "Don't end with a question — let them absorb first."
        )
    
    # Auto-decided: example
    elif intent in ["auto_example", "auto_example_for_affect", "auto_example_progress_based"]:
        guidance = (
            "Show them one clear, relatable example. Walk through it step by step. "
            "Use something from real life they'd actually encounter — money, sharing food, measuring things. "
            "Don't quiz at the end. Just say something like 'see how that works?' or 'make sense?'"
        )
    
    # Auto-decided: step-by-step
    elif intent in ["auto_step_by_step", "auto_step_by_step_procedural", "auto_step_by_step_progress_based"]:
        guidance = (
            "Break it into tiny steps. Show the FIRST step only, and walk through it. "
            "Don't overwhelm with all steps at once. Keep it very small."
        )
    
    # Micro-step (fallback auto-support for stuck students)
    elif intent == "micro_step_then_check":
        guidance = (
            "The student is stuck. Don't quiz them. Instead: "
            "1) Acknowledge that this is tricky. "
            "2) Teach ONE tiny piece of the concept using a BRAND NEW analogy (not food/pizza/chocolate — try something different like sharing stickers, dividing a rope, pouring water). "
            "3) End with 'does that make sense?' or 'take a moment and tell me what you think'. "
            "Do NOT ask a math question."
        )
    
    # Pure teaching mode (student is completely lost)
    elif intent == "pure_teach_no_quiz":
        guidance = (
            "The student is completely stuck. Stop all quizzing. Your ONLY job right now is to teach in the simplest possible way. "
            "Use a concrete, physical analogy (cutting a ribbon, sharing candies, filling cups). "
            "Explain JUST the core idea — what the concept means in plain words. "
            "End with something warm like 'let's just focus on understanding this first, no pressure.' "
            "Do NOT ask any question."
        )
    
    # Empathy-first (student repeatedly struggling)
    elif intent == "empathy_first_then_teach":
        guidance = (
            "The student has been struggling for a while. Start by genuinely empathizing — "
            "something like 'I know this feels hard right now' or 'hey, it's okay — everyone finds this confusing at first.' "
            "Then teach ONE small thing with a fresh analogy. "
            "Keep it very short. Don't quiz."
        )
    
    # Progress-aware pivots
    elif intent.startswith("progress_aware_pivot"):
        guidance = (
            "What you've been doing isn't working. Try a COMPLETELY different approach. "
            "If you were using food analogies, switch to money or physical objects. "
            "If you were explaining, try showing. If you were formal, be casual. "
            "Change your angle entirely."
        )
    
    elif intent == "progress_aware_reteach":
        guidance = (
            "The student was doing better before but has gotten confused again. "
            "Go back to the very basics with a fresh perspective. Use different words and analogies. "
            "Be encouraging — they CAN do this, they've shown it before."
        )
    
    # Acknowledge diagnostic response
    elif intent == "acknowledge_and_introduce_concept":
        guidance = (
            "The student shared what they find challenging. Briefly acknowledge that, "
            "then start teaching the concept. Don't ask another diagnostic question."
        )

    # MCQ: switch to multiple-choice (student was guessing)
    elif intent == "switch_to_mcq":
        guidance = (
            "The student gave a random or implausible answer (e.g. 9999, 100). "
            "Do NOT continue with an open-ended question. "
            "Restate the same concept as a multiple-choice question with exactly four options: A), B), C), D). "
            "Ask the student to choose one and to think before answering. "
            "Example: 'Hmm, let me ask this differently. Choose one: A) 2  B) 4  C) 8  D) 16. Think about it — which one makes sense?' "
            "Do NOT accept non-A/B/C/D answers in your next turn."
        )
    # MCQ: wrong answer, stay in MCQ with retry
    elif intent == "mcq_retry":
        guidance = (
            "The student is in multiple-choice mode and answered incorrectly. "
            "Present the SAME or a simpler question again as exactly four options A), B), C), D). "
            "Ask them to think and choose one of the options. "
            "Reject any response that is not clearly A, B, C, or D — politely ask them to pick one of the options."
        )
    # MCQ: correct answer — exit MCQ and reinforce briefly
    elif intent == "reinforce_exit_mcq":
        guidance = (
            "The student answered the multiple-choice question correctly. "
            "Give ONE brief sentence of reinforcement (e.g. 'Exactly!' or 'That\'s right.'). "
            "Then return to normal open-ended questions — do NOT stay in A/B/C/D mode. "
            "Ask a follow-up question at the same or slightly higher difficulty."
        )

    # Two consecutive wrong — simplify and use a different method
    elif intent == "simplify_and_change_method":
        guidance = (
            "The student got two answers wrong in a row. Do NOT repeat the same approach. "
            "Switch to a COMPLETELY different method: if you used numbers, try physical objects or a drawing; "
            "if you used one analogy, use a different one. Simplify the question. "
            "Then ask a simpler version of the same concept. Be encouraging but decisive."
        )
    # Correct answer and advancing — brief reinforcement then slightly harder
    elif intent == "reinforce_briefly_then_harder":
        guidance = (
            "The student answered correctly and is advancing. Give ONE specific sentence of reinforcement "
            "(e.g. 'You got the denominator right — that\'s the tricky part.'). Do NOT over-praise or repeat. "
            "Then ask a slightly harder question on the same concept. Keep it to one step up in difficulty."
        )
    
    # ----- Default kind-based guidance -----
    else:
        guidance_map = {
            TutorActionKind.ASK_QUESTION: (
                "Ask ONE clear, focused question. Keep it simple. "
                "Don't lecture before asking."
            ),
            TutorActionKind.ASK_MCQ: (
                "Present the question as multiple-choice only: A), B), C), D). "
                "Ask the student to think and choose one. Reject non-A/B/C/D answers by asking them to pick one of the options."
            ),
            TutorActionKind.GIVE_HINT: (
                "Give a small nudge in the right direction. Don't reveal the answer. "
                "Think of it like: 'what if you tried thinking about it this way...'"
            ),
            TutorActionKind.EXPLAIN_CONCEPT: (
                "Explain the concept clearly and simply. Use a relatable example. "
                "Keep it brief — 2-3 sentences max."
            ),
            TutorActionKind.BREAKDOWN_STEP: (
                "Break the problem into smaller steps. Show the process. "
                "Walk through it like you're solving it together."
            ),
            TutorActionKind.ENCOURAGE: (
                "Be warm and supportive. Acknowledge their effort specifically. "
                "Don't be generic — find something real to encourage about."
            ),
            TutorActionKind.CHECK_UNDERSTANDING: (
                "Ask a quick check question to see if they get it. "
                "Make it easier than the previous question."
            ),
            TutorActionKind.META_COACHING: (
                "Give a brief tip about HOW to approach these problems. "
                "Share a strategy, not just content."
            ),
            TutorActionKind.ADJUST_DIFFICULTY: (
                "Make the current task much simpler — like removing a step or "
                "using smaller numbers."
            ),
            TutorActionKind.SWITCH_OBJECTIVE: (
                "Transition smoothly to the next topic. Briefly celebrate what was done. "
                "Keep the transition natural."
            ),
            TutorActionKind.ESCALATE: (
                "Let them know a human teacher will help soon. Be reassuring and warm."
            ),
            TutorActionKind.END_LESSON: (
                "Wrap up naturally. Mention what was accomplished. End on a high note."
            ),
        }
        guidance = guidance_map.get(kind, "respond helpfully to the student")
    
    # Add encouragement note if needed
    if action_plan.include_encouragement:
        guidance += " Include brief, genuine encouragement — specific to what the student did, not generic."
    
    # Add difficulty adjustment note
    if action_plan.difficulty_adjustment == DifficultyAdjustment.EASIER:
        guidance += " Make this noticeably simpler than your previous response."
    elif action_plan.difficulty_adjustment == DifficultyAdjustment.HARDER:
        guidance += " Make this slightly more challenging."
    
    return guidance


def _build_user_prompt(
    action_plan: TutorActionPlan,
    lesson_context: Optional[Dict[str, Any]],
    objective_context: Optional[Dict[str, Any]],
    student_analysis: Optional[StudentTurnAnalysis],
    locale: str,
    chat_history: Optional[list],
    progress_evaluation: Optional[Any] = None,
    student_message: Optional[str] = None,
    last_tutor_message: Optional[str] = None,
) -> str:
    """Build the user prompt with rich context for generation."""
    parts = []
    
    language_name = _get_language_name(locale)
    parts.append(f"Respond in {language_name}.")
    parts.append("")
    
    # ===== Action plan summary =====
    parts.append(f"Action: {action_plan.kind.value}")
    if action_plan.intent_label:
        parts.append(f"Intent: {action_plan.intent_label}")
    parts.append("")

    # Auto-support metadata
    if action_plan.metadata.get("auto_support"):
        reason = action_plan.metadata.get("reason", "unknown")
        parts.append(f"[AI Decision: Auto-selected this approach because: {reason}]")
        parts.append("[Do NOT ask the student what kind of help they want. Just do it.]")
        parts.append("")

    # Request metadata
    if action_plan.metadata.get("triggered_by") == "student_request":
        request_type = action_plan.metadata.get("request_type", "unknown")
        parts.append(f"[Student explicitly asked for: {request_type} — do it immediately. Don't ask what they want.]")
        parts.append("")

    # ===== Lesson & Objectives overview =====
    if lesson_context:
        all_objectives = lesson_context.get("all_objectives", [])
        if all_objectives:
            parts.append("=== LESSON OBJECTIVES (this is what the student is learning today) ===")
            for obj in all_objectives:
                marker = "→ " if obj.get("is_current") else "  "
                state = obj.get("state", "unknown")
                title = obj.get("title", obj.get("id", "?"))
                state_label = {
                    "not_started": "⬜ not started",
                    "diagnosing": "🔍 diagnosing",
                    "exposing": "📖 explaining",
                    "supporting": "🤝 supporting",
                    "guided_practice": "✏️ practicing",
                    "independent_practice": "📝 independent",
                    "checking": "✅ checking mastery",
                    "consolidating": "🔄 consolidating",
                    "mastered": "🏆 mastered",
                    "escalate": "⚠️ escalated",
                }.get(state, state)
                parts.append(f"{marker}{title} [{state_label}]")
            parts.append("")
    
    # ===== Current objective detail =====
    if objective_context and objective_context.get("title"):
        parts.append(f"Current topic: {objective_context['title']}")
        if objective_context.get("teaching_state"):
            parts.append(f"Teaching stage: {objective_context['teaching_state']}")
        if objective_context.get("questions_asked") is not None:
            correct = objective_context.get("questions_correct", 0)
            total = objective_context.get("questions_asked", 0)
            if total > 0:
                parts.append(f"Student performance on this topic: {correct}/{total} correct")
        parts.append("")

    # ===== Progress evaluation =====
    if progress_evaluation:
        parts.append(f"Session progress: {progress_evaluation.signal.value} ({progress_evaluation.reasoning})")
        parts.append("")
    
    # ===== What the tutor last said =====
    if last_tutor_message:
        parts.append(f"Your last message was: \"{last_tutor_message[:400]}\"")
        parts.append("")

    # ===== What the student just said =====
    if student_message:
        parts.append(f"Student just said: \"{student_message}\"")
        parts.append("")

    # ===== Student analysis context =====
    if student_analysis:
        parts.append(f"Student's turn type: {student_analysis.kind.value}")
        if student_analysis.kind.value == "answer":
            parts.append(f"Correctness: {student_analysis.correctness.value}")
            if student_analysis.correctness.value != "correct" and student_analysis.error_category.value != "none":
                parts.append(f"Error type: {student_analysis.error_category.value}")
        if student_analysis.kind.value == "request" and student_analysis.request_type:
            parts.append(f"Request type: {student_analysis.request_type.value}")
        parts.append(f"Student mood: {student_analysis.affect.value}")
        parts.append("")

    # ===== Conversation history =====
    if chat_history:
        parts.append("--- CONVERSATION SO FAR (read carefully to avoid repetition) ---")
        for item in chat_history[-12:]:
            role = item.get("role", "unknown")
            content = item.get("content", "")
            content = content[:500].replace("\n", " ").strip()
            label = "TUTOR" if role in ["assistant", "tutor"] else "STUDENT"
            parts.append(f"{label}: {content}")
        parts.append("--- END CONVERSATION ---")
        parts.append("")
        parts.append("CRITICAL: Do NOT repeat any analogy, example, phrase, or structure from the conversation above. Every response must be fresh and different.")
        parts.append("")
    
    parts.append("Generate your response now. Remember: be natural, be brief (2-4 sentences), and NEVER ask the student how they'd like to be helped.")
    
    return "\n".join(parts)
