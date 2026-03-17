"""Repository for TutorSession model operations"""
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TutorSession
from app.repositories.base import BaseRepository


class TutorSessionRepository(BaseRepository[TutorSession]):
    """Repository for TutorSession CRUD operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(TutorSession, session)
    
    async def create_session(
        self,
        tenant_id: str,
        student_id: str,
        lesson_id: str,
        objective_ids: List[str],
        ou_id: Optional[str] = None,
        region_id: Optional[str] = None,
        program_id: Optional[str] = None,
        context_scopes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TutorSession:
        """
        Create a new tutoring session.
        
        Args:
            tenant_id: Tenant identifier
            student_id: Student identifier
            lesson_id: Lesson identifier
            objective_ids: List of objective IDs for this session
            ou_id: Organization Unit ID (optional)
            region_id: Region/country identifier (optional)
            program_id: Program/year ID (optional, e.g., "Grade1-Math-2025")
            context_scopes: Resolved visibility scopes (optional)
            metadata: Additional metadata (optional)
            
        Returns:
            Created TutorSession instance
        """
        return await self.create(
            tenant_id=tenant_id,
            student_id=student_id,
            lesson_id=lesson_id,
            objective_ids=objective_ids,
            ou_id=ou_id,
            region_id=region_id,
            program_id=program_id,
            context_scopes=context_scopes or [],
            status="active",
            session_metadata=metadata or {},
        )
    
    async def get_session_by_id(
        self,
        tenant_id: str,
        session_id: UUID
    ) -> Optional[TutorSession]:
        """
        Get a session by ID with tenant safety.
        
        Args:
            tenant_id: Tenant identifier
            session_id: Session UUID
            
        Returns:
            TutorSession instance or None if not found
        """
        result = await self.session.execute(
            select(TutorSession)
            .where(
                TutorSession.id == session_id,
                TutorSession.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()
    
    async def update_session(
        self,
        tenant_id: str,
        session_id: UUID,
        **fields
    ) -> Optional[TutorSession]:
        """
        Update a session's fields.
        
        Args:
            tenant_id: Tenant identifier
            session_id: Session UUID
            **fields: Fields to update (status, current_objective_id, etc.)
            
        Returns:
            Updated TutorSession or None if not found
        """
        from sqlalchemy.orm.attributes import flag_modified
        import logging
        logger = logging.getLogger(__name__)
        
        session = await self.get_session_by_id(tenant_id, session_id)
        if not session:
            return None
        
        logger.info(f"[DEBUG] update_session called with fields: {list(fields.keys())}")
        
        for key, value in fields.items():
            if hasattr(session, key):
                setattr(session, key, value)
                logger.info(f"[DEBUG] Setting {key} = {str(value)[:100]}...")
                # For JSONB fields, explicitly mark as modified
                if key == 'session_metadata':
                    flag_modified(session, 'session_metadata')
                    logger.info(f"[DEBUG] Flagged session_metadata as modified")
        
        await self.session.flush()
        await self.session.refresh(session)
        return session
    
    async def get_sessions_by_student(
        self,
        tenant_id: str,
        student_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[TutorSession]:
        """
        Get all sessions for a specific student.
        
        Args:
            tenant_id: Tenant identifier
            student_id: Student identifier
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of sessions for the student
        """
        result = await self.session.execute(
            select(TutorSession)
            .where(
                TutorSession.tenant_id == tenant_id,
                TutorSession.student_id == student_id
            )
            .order_by(TutorSession.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def get_active_sessions(
        self,
        tenant_id: str,
        limit: int = 100
    ) -> List[TutorSession]:
        """
        Get all active sessions for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of records
            
        Returns:
            List of active sessions
        """
        result = await self.session.execute(
            select(TutorSession)
            .where(
                TutorSession.tenant_id == tenant_id,
                TutorSession.status == "active"
            )
            .order_by(TutorSession.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_sessions_by_lesson(
        self,
        tenant_id: str,
        lesson_id: str,
        limit: int = 100
    ) -> List[TutorSession]:
        """
        Get sessions for a specific lesson.
        
        Args:
            tenant_id: Tenant identifier
            lesson_id: Lesson identifier
            limit: Maximum number of records
            
        Returns:
            List of sessions for the lesson
        """
        result = await self.session.execute(
            select(TutorSession)
            .where(
                TutorSession.tenant_id == tenant_id,
                TutorSession.lesson_id == lesson_id
            )
            .order_by(TutorSession.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_sessions_by_ou(
        self,
        tenant_id: str,
        ou_id: str,
        limit: int = 100
    ) -> List[TutorSession]:
        """
        Get sessions for a specific OU.
        
        Args:
            tenant_id: Tenant identifier
            ou_id: Organization Unit identifier
            limit: Maximum number of records
            
        Returns:
            List of sessions for the OU
        """
        result = await self.session.execute(
            select(TutorSession)
            .where(
                TutorSession.tenant_id == tenant_id,
                TutorSession.ou_id == ou_id
            )
            .order_by(TutorSession.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

