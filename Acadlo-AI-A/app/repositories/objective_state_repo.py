"""Repository for ObjectiveState model operations"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ObjectiveState
from app.repositories.base import BaseRepository


class ObjectiveStateRepository(BaseRepository[ObjectiveState]):
    """Repository for ObjectiveState CRUD operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(ObjectiveState, session)
    
    async def create_objective_state(
        self,
        tenant_id: str,
        session_id: UUID,
        objective_id: str,
        initial_state: str = "not_started"
    ) -> ObjectiveState:
        """
        Create initial state for an objective.
        
        Args:
            tenant_id: Tenant identifier
            session_id: Session UUID
            objective_id: Objective identifier
            initial_state: Initial teaching state (default: "not_started")
            
        Returns:
            Created ObjectiveState instance
        """
        return await self.create(
            tenant_id=tenant_id,
            session_id=session_id,
            objective_id=objective_id,
            state=initial_state,
            questions_asked=0,
            questions_correct=0,
            questions_incorrect=0,
            last_error_types=[],
            mastery_estimate="low",
            extra={},
        )
    
    async def get_objective_states_for_session(
        self,
        tenant_id: str,
        session_id: UUID
    ) -> List[ObjectiveState]:
        """
        Fetch all objective states for a session.
        
        Args:
            tenant_id: Tenant identifier
            session_id: Session UUID
            
        Returns:
            List of ObjectiveState instances
        """
        result = await self.session.execute(
            select(ObjectiveState)
            .where(
                ObjectiveState.tenant_id == tenant_id,
                ObjectiveState.session_id == session_id
            )
            .order_by(ObjectiveState.created_at)
        )
        return list(result.scalars().all())
    
    async def get_objective_state(
        self,
        tenant_id: str,
        session_id: UUID,
        objective_id: str
    ) -> Optional[ObjectiveState]:
        """
        Fetch a single objective state.
        
        Args:
            tenant_id: Tenant identifier
            session_id: Session UUID
            objective_id: Objective identifier
            
        Returns:
            ObjectiveState instance or None if not found
        """
        result = await self.session.execute(
            select(ObjectiveState)
            .where(
                ObjectiveState.tenant_id == tenant_id,
                ObjectiveState.session_id == session_id,
                ObjectiveState.objective_id == objective_id
            )
        )
        return result.scalar_one_or_none()
    
    async def update_objective_state(
        self,
        tenant_id: str,
        session_id: UUID,
        objective_id: str,
        **fields
    ) -> Optional[ObjectiveState]:
        """
        Update an objective state's fields.
        
        Args:
            tenant_id: Tenant identifier
            session_id: Session UUID
            objective_id: Objective identifier
            **fields: Fields to update (state, questions_asked, mastery_estimate, etc.)
            
        Returns:
            Updated ObjectiveState or None if not found
        """
        obj_state = await self.get_objective_state(tenant_id, session_id, objective_id)
        if not obj_state:
            return None
        
        for key, value in fields.items():
            if hasattr(obj_state, key):
                setattr(obj_state, key, value)
        
        await self.session.flush()
        await self.session.refresh(obj_state)
        return obj_state
    
    async def save_objective_state(
        self,
        state: ObjectiveState
    ) -> None:
        """
        Save an objective state (for use when state is already in memory).
        
        Args:
            state: ObjectiveState instance to save
        """
        await self.session.flush()
        await self.session.refresh(state)
    
    async def get_states_by_objective(
        self,
        tenant_id: str,
        objective_id: str,
        limit: int = 100
    ) -> List[ObjectiveState]:
        """
        Get all states for a specific objective across sessions (for analytics).
        
        Args:
            tenant_id: Tenant identifier
            objective_id: Objective identifier
            limit: Maximum number of records
            
        Returns:
            List of ObjectiveState instances
        """
        result = await self.session.execute(
            select(ObjectiveState)
            .where(
                ObjectiveState.tenant_id == tenant_id,
                ObjectiveState.objective_id == objective_id
            )
            .order_by(ObjectiveState.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

