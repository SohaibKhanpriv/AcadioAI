"""Repository for StudentProfile model operations"""
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.models import StudentProfile, ObjectiveState
from app.repositories.base import BaseRepository


class StudentProfileRepository(BaseRepository[StudentProfile]):
    """Repository for StudentProfile CRUD operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(StudentProfile, session)
    
    async def get_or_create_student_profile(
        self,
        tenant_id: str,
        student_id: str,
        initial_ou_id: Optional[str] = None,
        primary_language: Optional[str] = None,
        grade_band: Optional[str] = None,
        region_id: Optional[str] = None
    ) -> StudentProfile:
        """
        Get existing student profile or create if it doesn't exist.
        
        Args:
            tenant_id: Tenant identifier
            student_id: Student identifier
            initial_ou_id: Primary OU to set on creation (optional)
            primary_language: Student's primary language (optional)
            grade_band: Student's grade band (optional)
            region_id: Student's region (optional)
            
        Returns:
            StudentProfile instance (existing or newly created)
        """
        # Try to get existing profile
        profile = await self.get_student_profile(tenant_id, student_id)
        
        if profile:
            return profile
        
        # Create new profile
        try:
            profile = await self.create(
                tenant_id=tenant_id,
                student_id=student_id,
                primary_ou_id=initial_ou_id,
                ou_memberships=[],
                primary_language=primary_language,
                grade_band=grade_band,
                region_id=region_id,
                objective_stats={},
                pace_estimate="unknown",
                engagement_estimate="unknown",
            )
            return profile
        except IntegrityError:
            # Race condition: another process created the profile
            # Roll back and fetch the existing one
            await self.session.rollback()
            profile = await self.get_student_profile(tenant_id, student_id)
            if not profile:
                raise Exception(f"Failed to get or create profile for student {student_id}")
            return profile
    
    async def get_student_profile(
        self,
        tenant_id: str,
        student_id: str
    ) -> Optional[StudentProfile]:
        """
        Get a student profile by tenant and student ID.
        
        Args:
            tenant_id: Tenant identifier
            student_id: Student identifier
            
        Returns:
            StudentProfile instance or None if not found
        """
        result = await self.session.execute(
            select(StudentProfile)
            .where(
                StudentProfile.tenant_id == tenant_id,
                StudentProfile.student_id == student_id
            )
        )
        return result.scalar_one_or_none()
    
    async def update_student_profile(
        self,
        tenant_id: str,
        student_id: str,
        **fields
    ) -> Optional[StudentProfile]:
        """
        Update a student profile's fields.
        
        Args:
            tenant_id: Tenant identifier
            student_id: Student identifier
            **fields: Fields to update (pace_estimate, engagement_estimate, etc.)
            
        Returns:
            Updated StudentProfile or None if not found
        """
        profile = await self.get_student_profile(tenant_id, student_id)
        if not profile:
            return None
        
        for key, value in fields.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        await self.session.flush()
        await self.session.refresh(profile)
        return profile
    
    async def update_student_profile_from_objective_state(
        self,
        profile: StudentProfile,
        objective_state: ObjectiveState
    ) -> StudentProfile:
        """
        Update student profile aggregates based on completed objective state.
        
        This should be called when an objective reaches a terminal state
        (MASTERED or ESCALATE) to update the student's historical stats.
        
        Args:
            profile: StudentProfile instance to update
            objective_state: Completed ObjectiveState
            
        Returns:
            Updated StudentProfile instance
        """
        objective_id = objective_state.objective_id
        
        # Get or initialize stats for this objective
        if objective_id not in profile.objective_stats:
            profile.objective_stats[objective_id] = {
                "total_sessions": 0,
                "total_questions": 0,
                "total_correct": 0,
                "last_mastery_estimate": "low"
            }
        
        stats = profile.objective_stats[objective_id]
        
        # Update aggregated stats
        stats["total_sessions"] += 1
        stats["total_questions"] += objective_state.questions_asked
        stats["total_correct"] += objective_state.questions_correct
        stats["last_mastery_estimate"] = objective_state.mastery_estimate
        
        # Mark profile as modified (SQLAlchemy doesn't auto-detect JSONB changes)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(profile, "objective_stats")
        
        await self.session.flush()
        await self.session.refresh(profile)
        return profile
    
    async def get_profiles_by_ou(
        self,
        tenant_id: str,
        ou_id: str,
        limit: int = 100
    ) -> list[StudentProfile]:
        """
        Get student profiles for a specific OU (for OU-level analytics).
        
        Args:
            tenant_id: Tenant identifier
            ou_id: Organization Unit identifier
            limit: Maximum number of records
            
        Returns:
            List of StudentProfile instances
        """
        result = await self.session.execute(
            select(StudentProfile)
            .where(
                StudentProfile.tenant_id == tenant_id,
                StudentProfile.primary_ou_id == ou_id
            )
            .order_by(StudentProfile.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

