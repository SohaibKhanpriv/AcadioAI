"""
Lesson generation: when no lesson_id is provided, find or generate a lesson for the student.

Finds existing StudentLesson by topic for the student, or generates via LLM and saves.
"""
import json
import re
import logging
from typing import List, Dict, Any, Optional

from app.tutor.graph_context import TutorGraphContext
from app.providers.llm import get_llm_provider, LLMMessage
from app.core.config import settings

logger = logging.getLogger(__name__)


def _slug(text: str, max_len: int = 50) -> str:
    """Turn text into a safe slug."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return (s or "unknown")[:max_len]


def _default_objectives_for_topic(topic: str, grade: str, level: str) -> List[Dict[str, Any]]:
    """Return a minimal default set of objectives when LLM fails or is skipped."""
    topic_slug = _slug(topic, 30)
    return [
        {"objective_id": f"obj_{topic_slug}_intro", "title": f"Introduction to {topic}", "description": None},
        {"objective_id": f"obj_{topic_slug}_practice", "title": f"Practice {topic}", "description": None},
    ]


async def _generate_lesson_via_llm(
    topic: str,
    grade: str,
    level: str,
    language: str,
    tenant_id: str,
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Call LLM to generate a lesson title and 2–5 learning objectives.
    Returns (title, list of {objective_id, title, description}).
    """
    prompt = f"""Generate a short lesson plan for teaching "{topic}" to a student in grade {grade} at "{level}" level. Language: {language}.

Return ONLY a valid JSON object with this exact structure (no markdown, no extra text):
{{
  "title": "A short lesson title",
  "objectives": [
    {{ "title": "First learning objective", "description": "Optional one-line description" }},
    {{ "title": "Second objective", "description": null }}
  ]
}}
Provide 2 to 5 objectives. Use clear, age-appropriate language. objective_id will be generated from the title."""

    try:
        llm = get_llm_provider()
        response = await llm.generate(
            messages=[
                LLMMessage(role="system", content="You output only valid JSON. No markdown code fences, no explanation."),
                LLMMessage(role="user", content=prompt),
            ],
            model=settings.TUTOR_LLM_MODEL,
            temperature=0.5,
            max_tokens=800,
            tenant_id=tenant_id,
            scenario="lesson_generation",
        )
        text = (response.content or "").strip()
        # Strip markdown code block if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        data = json.loads(text)
        title = (data.get("title") or f"Introduction to {topic}").strip()
        raw_obj = data.get("objectives") or []
        objectives = []
        for i, o in enumerate(raw_obj[:5]):
            t = (o.get("title") or f"Objective {i+1}").strip()
            desc = (o.get("description") or "").strip() or None
            obj_id = f"obj_{_slug(t, 40)}"
            if any(x["objective_id"] == obj_id for x in objectives):
                obj_id = f"obj_{_slug(t, 35)}_{i}"
            objectives.append({"objective_id": obj_id, "title": t, "description": desc})
        if not objectives:
            raise ValueError("No objectives in LLM response")
        return title, objectives
    except Exception as e:
        logger.warning(f"LLM lesson generation failed: {e}, using defaults")
        return f"Introduction to {topic}", _default_objectives_for_topic(topic, grade, level)


async def get_or_create_lesson_for_session(
    state: TutorGraphContext,
) -> tuple[str, List[str], Dict[str, str]]:
    """
    Resolve lesson_id and objective_ids for this session when they were pending.
    - If we have onboarding_answers with topic, look up StudentLesson for this student+topic.
    - If found, return (lesson_id, objective_ids, objective_labels).
    - If not found, generate a lesson (LLM or default), save to StudentLesson + StudentLessonObjective, return ids.

    Returns:
        (lesson_id, objective_ids, objective_labels)
    """
    from app.repositories import StudentLessonRepository

    answers = state.onboarding_answers or {}
    topic = (answers.get("topic") or "").strip() or "general"
    grade = (answers.get("grade") or "").strip() or "4"
    level = (answers.get("level") or "").strip() or "beginner"
    language = (answers.get("language") or "").strip() or "en"

    repo = StudentLessonRepository(state.db_session)
    existing = await repo.find_lesson_by_topic(
        tenant_id=state.tenant_id,
        student_id=state.student_id,
        topic=topic,
    )
    if existing:
        objective_ids = [o.objective_id for o in existing.objectives]
        labels = {o.objective_id: o.title for o in existing.objectives}
        logger.info(f"Reusing existing StudentLesson {existing.lesson_id} for topic={topic}")
        return existing.lesson_id, objective_ids, labels

    # Generate new lesson via LLM (fallback to default if LLM fails)
    title, objectives = await _generate_lesson_via_llm(
        topic=topic,
        grade=grade,
        level=level,
        language=language,
        tenant_id=state.tenant_id,
    )
    lesson_id = f"lesson_{_slug(topic)}_{_slug(grade)}_{_slug(level)}"

    lesson = await repo.create_lesson(
        tenant_id=state.tenant_id,
        student_id=state.student_id,
        lesson_id=lesson_id,
        topic=topic,
        title=title,
        objectives=objectives,
        grade=grade,
        skill_level=level,
        language=language,
        source="llm_generated",
    )
    await state.db_session.flush()
    objective_ids = [o["objective_id"] for o in objectives]
    labels = {o["objective_id"]: o["title"] for o in objectives}
    logger.info(f"Created new StudentLesson {lesson_id} with {len(objective_ids)} objectives")
    return lesson_id, objective_ids, labels
