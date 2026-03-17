"""Repository for StudentLesson and StudentLessonObjective."""
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import StudentLesson, StudentLessonObjective
from app.repositories.base import BaseRepository


class StudentLessonRepository(BaseRepository[StudentLesson]):
    """Repository for StudentLesson and related StudentLessonObjective CRUD."""

    def __init__(self, session: AsyncSession):
        super().__init__(StudentLesson, session)

    async def create_lesson(
        self,
        tenant_id: str,
        student_id: str,
        lesson_id: str,
        topic: str,
        title: str,
        objectives: List[Dict[str, Any]],
        grade: Optional[str] = None,
        skill_level: Optional[str] = None,
        language: Optional[str] = None,
        source: str = "llm_generated",
        lesson_metadata: Optional[Dict[str, Any]] = None,
    ) -> StudentLesson:
        """
        Create a StudentLesson and its StudentLessonObjective records.

        objectives: list of {"objective_id": str, "title": str, "description": str | None}
        """
        lesson = await self.create(
            tenant_id=tenant_id,
            student_id=student_id,
            lesson_id=lesson_id,
            topic=topic,
            title=title,
            grade=grade,
            skill_level=skill_level,
            language=language,
            source=source,
            lesson_metadata=lesson_metadata or {},
        )
        for idx, obj in enumerate(objectives):
            obj_record = StudentLessonObjective(
                tenant_id=tenant_id,
                student_lesson_id=lesson.id,
                objective_id=obj["objective_id"],
                title=obj["title"],
                description=obj.get("description"),
                display_order=idx,
            )
            self.session.add(obj_record)
        await self.session.flush()
        await self.session.refresh(lesson)
        return lesson

    async def get_lesson_by_id(
        self,
        tenant_id: str,
        lesson_uuid: UUID,
    ) -> Optional[StudentLesson]:
        """Get a lesson by its UUID with objectives loaded. Tenant-scoped."""
        result = await self.session.execute(
            select(StudentLesson)
            .where(
                StudentLesson.id == lesson_uuid,
                StudentLesson.tenant_id == tenant_id,
            )
            .options(selectinload(StudentLesson.objectives))
        )
        return result.scalar_one_or_none()

    async def get_lessons_for_student(
        self,
        tenant_id: str,
        student_id: str,
        limit: int = 50,
    ) -> List[StudentLesson]:
        """List lessons for a student, most recent first."""
        result = await self.session.execute(
            select(StudentLesson)
            .where(
                StudentLesson.tenant_id == tenant_id,
                StudentLesson.student_id == student_id,
            )
            .order_by(StudentLesson.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_lesson_by_topic(
        self,
        tenant_id: str,
        student_id: str,
        topic: str,
    ) -> Optional[StudentLesson]:
        """
        Find a lesson for this student with the given topic (normalized).
        Returns the first match (e.g. most recent). Use for reuse before generating.
        """
        topic_normalized = topic.strip().lower()
        result = await self.session.execute(
            select(StudentLesson)
            .where(
                StudentLesson.tenant_id == tenant_id,
                StudentLesson.student_id == student_id,
            )
            .options(selectinload(StudentLesson.objectives))
            .order_by(StudentLesson.created_at.desc())
        )
        for lesson in result.scalars().all():
            if lesson.topic.strip().lower() == topic_normalized:
                return lesson
        return None
