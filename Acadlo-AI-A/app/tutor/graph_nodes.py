"""
LangGraph nodes for the Tutor Runtime Engine.

Each node is an async function that takes TutorGraphContext and returns updated context.
"""
import logging
from datetime import datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.tutor.graph_context import TutorGraphContext
from app.tutor.enums import TutorSessionStatus, ObjectiveTeachingState, MasteryEstimate
from app.tutor.types import (
    ObjectivePerformanceSnapshot,
    ObjectiveTeachingConfig,
    DEFAULT_TUTOR_BEHAVIOR_CONFIG,
)
from app.tutor.state_machine_integration import (
    apply_objective_state_transition,
    ApplyObjectiveTransitionArgs
)
from app.repositories import (
    TutorSessionRepository,
    ObjectiveStateRepository,
    StudentProfileRepository,
)

from app.tutor.onboarding import (
    get_required_onboarding_questions,
    is_onboarding_complete,
    get_next_onboarding_question,
    parse_onboarding_response,
    merge_onboarding_answers,
    get_onboarding_question_prompt,
    get_full_onboarding_prompt,
    get_redirect_to_question_message,
)

logger = logging.getLogger(__name__)


def _get_locale_from_state(state: TutorGraphContext) -> str:
    """Get locale from session metadata or context."""
    if state.session and state.session.session_metadata:
        loc = state.session.session_metadata.get("locale")
        if loc:
            return loc
    if getattr(state, "locale_hint", None):
        return state.locale_hint
    return "en-US"


# =============================================================================
# Node: Load Session and Profile
# =============================================================================

async def load_session_and_profile(
    state: TutorGraphContext
) -> TutorGraphContext:
    """
    Load or create TutorSession, ObjectiveStates, and StudentProfile.
    
    If session_id is provided: load existing session
    If session_id is None: create new session (start case)
    
    For new sessions, locale is stored in session_metadata.
    For existing sessions, locale is read from session_metadata.
    """
    session_repo = TutorSessionRepository(state.db_session)
    objective_repo = ObjectiveStateRepository(state.db_session)
    profile_repo = StudentProfileRepository(state.db_session)
    
    # Load or create StudentProfile first
    student_profile = await profile_repo.get_or_create_student_profile(
        tenant_id=state.tenant_id,
        student_id=state.student_id,
        initial_ou_id=state.ou_id,
        region_id=state.region_id
    )
    state.student_profile = student_profile
    
    if state.session_id:
        # Continue case: load existing session
        tutor_session = await session_repo.get_session_by_id(
            tenant_id=state.tenant_id,
            session_id=state.session_id
        )
        
        if not tutor_session:
            raise Exception(f"TutorSession not found: {state.session_id} for tenant {state.tenant_id}")
        
        # DEBUG: Log what metadata was loaded from DB
        logger.info(f"[DEBUG] Loaded session from DB. session_id={tutor_session.id}")
        logger.info(f"[DEBUG] session_metadata from DB: {tutor_session.session_metadata}")
        
        # Validate tenant match
        if tutor_session.tenant_id != state.tenant_id:
            raise ValueError(f"Tenant mismatch: session belongs to different tenant")
        
        # Check if session is terminal
        if tutor_session.status == "completed":
            raise ValueError(f"Session is complete and cannot accept new turns")
        
        # Load all objective states for this session
        objective_states = await objective_repo.get_objective_states_for_session(
            tenant_id=state.tenant_id,
            session_id=tutor_session.id
        )
        
        # Populate context from loaded session
        state.session = tutor_session
        state.lesson_id = tutor_session.lesson_id
        state.student_id = tutor_session.student_id
        state.objective_ids = tutor_session.objective_ids
        state.ou_id = tutor_session.ou_id
        state.context_scopes = tutor_session.context_scopes
        state.program_id = tutor_session.program_id
        state.region_id = tutor_session.region_id
        state.current_objective_id = tutor_session.current_objective_id
        state.objectives = {obj.objective_id: obj for obj in objective_states}
        state.is_new_session = False

        # Load chat history and streaks from session metadata
        session_metadata = tutor_session.session_metadata or {}
        state.chat_history = session_metadata.get("chat_history", [])
        state.last_tutor_message = session_metadata.get("last_tutor_message")
        state.no_answer_streak = session_metadata.get("no_answer_streak", 0)
        state.objective_labels = session_metadata.get("objective_labels", {})
        
        logger.info(f"Loaded existing session {state.session_id} with {len(objective_states)} objectives")
    
    else:
        # Start case: create new session
        # Get locale from the context field (could be dataclass or dict after LangGraph)
        if isinstance(state, dict):
            locale = state.get('locale_hint') or "ar-JO"
        else:
            locale = getattr(state, 'locale_hint', None) or "ar-JO"
        
        # Build session metadata with locale
        session_metadata = {
            "locale": locale,
            "chat_history": [],
            "no_answer_streak": 0,
            "objective_labels": state.objective_labels or {},
        }
        
        tutor_session = await session_repo.create_session(
            tenant_id=state.tenant_id,
            student_id=state.student_id,
            lesson_id=state.lesson_id,
            objective_ids=state.objective_ids,
            ou_id=state.ou_id,
            region_id=state.region_id,
            program_id=state.program_id,
            context_scopes=state.context_scopes,
            metadata=session_metadata
        )
        
        # Commit to get the session ID
        await state.db_session.commit()
        await state.db_session.refresh(tutor_session)
        
        # Create initial ObjectiveState for each objective (skip when lesson is pending)
        objective_states = []
        lesson_id_lower = (state.lesson_id or "").strip().lower()
        obj_ids = state.objective_ids or []
        if lesson_id_lower not in ("pending", "") and obj_ids and not (
            len(obj_ids) == 1 and (obj_ids[0] or "").strip().lower() == "pending"
        ):
            for obj_id in obj_ids:
                if not (obj_id or "").strip():
                    continue
                obj_state = await objective_repo.create_objective_state(
                    tenant_id=state.tenant_id,
                    session_id=tutor_session.id,
                    objective_id=obj_id,
                    initial_state=ObjectiveTeachingState.NOT_STARTED.value
                )
                objective_states.append(obj_state)
        
        await state.db_session.commit()
        
        # Populate context
        state.session = tutor_session
        state.session_id = str(tutor_session.id)
        state.objectives = {obj.objective_id: obj for obj in objective_states}
        state.is_new_session = True
        
        logger.info(f"Created new session {state.session_id} with {len(objective_states)} objectives, locale={locale}")
    
    return state


# =============================================================================
# Node: Onboarding Check
# =============================================================================

async def onboarding_check(state: TutorGraphContext) -> TutorGraphContext:
    """
    Determine if we need to collect onboarding (topic, grade, level, language).
    If onboarding is complete, set onboarding_complete and needs_lesson_generation.
    Otherwise set next_onboarding_question and onboarding_answers for generate_onboarding_response.
    """
    lesson_id = (state.lesson_id or "").strip()
    objective_ids = state.objective_ids or []
    profile = state.student_profile
    required = get_required_onboarding_questions(lesson_id, objective_ids, profile)

    # Nothing to ask: skip onboarding
    if not required:
        state.onboarding_complete = True
        state.needs_lesson_generation = (
            lesson_id.lower() in ("pending", "") or not objective_ids
        )
        state.onboarding_required = []
        state.onboarding_answers = {}
        state.next_onboarding_question = None
        logger.info("Onboarding skipped: no questions required")
        return state

    # Load existing onboarding state from session
    session_metadata = (state.session and state.session.session_metadata) or {}
    onboarding = session_metadata.get("onboarding") or {}
    answers = dict(onboarding.get("answers") or {})

    # If we have a student message this turn, parse and merge
    if state.student_message and state.student_message.strip():
        locale = _get_locale_from_state(state)
        # Determine the question we're currently waiting for (context for parser)
        pending_q = get_next_onboarding_question(required, answers)
        new_extracted = parse_onboarding_response(
            state.student_message, required, locale,
            current_question=pending_q,
        )
        answers = merge_onboarding_answers(answers, new_extracted)
        # Persist back to session metadata (will be saved in save_session_and_profile)
        if state.session:
            meta = dict(state.session.session_metadata or {})
            if "onboarding" not in meta:
                meta["onboarding"] = {}
            meta["onboarding"]["answers"] = answers
            state.session.session_metadata = meta

    state.onboarding_answers = answers
    state.onboarding_required = required
    next_q = get_next_onboarding_question(required, answers)
    state.next_onboarding_question = next_q

    if next_q is None:
        # All required answers collected
        state.onboarding_complete = True
        state.needs_lesson_generation = (
            lesson_id.lower() in ("pending", "") or not objective_ids
        )
        # Persist to StudentProfile
        if profile and state.tenant_id and state.student_id:
            profile_repo = StudentProfileRepository(state.db_session)
            await profile_repo.update_student_profile(
                tenant_id=state.tenant_id,
                student_id=state.student_id,
                grade_band=answers.get("grade") or profile.grade_band,
                skill_level=answers.get("level") or profile.skill_level,
                primary_language=answers.get("language") or profile.primary_language,
            )
            await state.db_session.flush()
        # Mark onboarding complete in session metadata
        if state.session:
            meta = dict(state.session.session_metadata or {})
            if "onboarding" not in meta:
                meta["onboarding"] = {}
            meta["onboarding"]["complete"] = True
            meta["onboarding"]["answers"] = answers
            state.session.session_metadata = meta
        logger.info("Onboarding complete, answers persisted to profile")
    return state


async def generate_onboarding_response(state: TutorGraphContext) -> TutorGraphContext:
    """
    Generate the tutor reply for onboarding: either ask the next question
    or redirect the student back to the question if they chatted instead.
    """
    locale = _get_locale_from_state(state)
    next_q = state.next_onboarding_question
    required = state.onboarding_required or []

    # First turn (no student message): show the full question block
    if not (state.student_message and state.student_message.strip()):
        if len(required) >= 2:
            state.tutor_reply = get_full_onboarding_prompt(locale)
        elif next_q:
            state.tutor_reply = get_onboarding_question_prompt(next_q, locale, 1, len(required))
        else:
            state.tutor_reply = get_full_onboarding_prompt(locale)
        return state

    # We have a student message AND a next question still pending.
    # The parser already ran in onboarding_check. If next_q is still set
    # it means the student's answer didn't satisfy it → redirect.
    if next_q:
        state.tutor_reply = get_redirect_to_question_message(next_q, locale)
        return state

    # Shouldn't get here (onboarding should be complete), but just in case:
    state.tutor_reply = get_full_onboarding_prompt(locale)
    return state


# =============================================================================
# Node: Resolve Lesson (when no lesson was provided)
# =============================================================================

async def resolve_lesson(state: TutorGraphContext) -> TutorGraphContext:
    """
    When needs_lesson_generation is True, find or generate a lesson from onboarding
    answers, update the session, and create ObjectiveState records.
    Otherwise no-op.
    """
    if not getattr(state, "needs_lesson_generation", False):
        logger.info("resolve_lesson: no lesson generation needed")
        return state

    from app.tutor.lesson_generator import get_or_create_lesson_for_session

    lesson_id, objective_ids, objective_labels = await get_or_create_lesson_for_session(state)
    state.lesson_id = lesson_id
    state.objective_ids = objective_ids
    state.objective_labels = objective_labels

    # Update session in DB
    session_repo = TutorSessionRepository(state.db_session)
    meta = dict(state.session.session_metadata or {})
    meta["objective_labels"] = objective_labels
    await session_repo.update_session(
        tenant_id=state.tenant_id,
        session_id=state.session.id,
        lesson_id=lesson_id,
        objective_ids=objective_ids,
        session_metadata=meta,
    )
    await state.db_session.flush()

    # Create ObjectiveState for each objective
    objective_repo = ObjectiveStateRepository(state.db_session)
    state.objectives = {}
    for obj_id in objective_ids:
        obj_state = await objective_repo.create_objective_state(
            tenant_id=state.tenant_id,
            session_id=state.session.id,
            objective_id=obj_id,
            initial_state=ObjectiveTeachingState.NOT_STARTED.value,
        )
        state.objectives[obj_id] = obj_state
    await state.db_session.commit()
    logger.info(f"resolve_lesson: set lesson_id={lesson_id}, {len(objective_ids)} objectives")
    return state


# =============================================================================
# Node: Select Current Objective
# =============================================================================

async def select_current_objective(state: TutorGraphContext) -> TutorGraphContext:
    """
    Determine which objective should be the current objective.
    
    Strategy (v1):
    - If session.current_objective_id is set and that objective is not terminal (MASTERED/ESCALATE),
      continue with it.
    - Otherwise, pick the first objective that is not in MASTERED or ESCALATE state.
    - Set objective_config for the selected objective.
    """
    # Check if current_objective_id is already set and valid
    if state.current_objective_id:
        current_obj_state = state.objectives.get(state.current_objective_id)
        if current_obj_state:
            current_state = ObjectiveTeachingState(current_obj_state.state)
            # If not terminal, keep it
            if current_state not in [ObjectiveTeachingState.MASTERED, ObjectiveTeachingState.ESCALATE]:
                logger.info(f"Continuing with current objective: {state.current_objective_id}")
                state.objective_config = _get_objective_config(state, state.current_objective_id)
                return state
    
    # Find first non-terminal objective
    for obj_id in state.objective_ids:
        obj_state = state.objectives.get(obj_id)
        if obj_state:
            obj_teaching_state = ObjectiveTeachingState(obj_state.state)
            if obj_teaching_state not in [ObjectiveTeachingState.MASTERED, ObjectiveTeachingState.ESCALATE]:
                state.current_objective_id = obj_id
                state.objective_config = _get_objective_config(state, obj_id)
                logger.info(f"Selected new current objective: {obj_id}")
                return state
    
    # All objectives are terminal
    state.current_objective_id = None
    state.objective_config = None
    logger.info("All objectives are MASTERED or ESCALATE")
    return state


def _get_objective_config(state: TutorGraphContext, objective_id: str) -> ObjectiveTeachingConfig:
    """Helper to get config for an objective"""
    if state.lesson_config:
        return state.lesson_config.get_config(objective_id)
    # Return default config
    return ObjectiveTeachingConfig(objective_id=objective_id)


# =============================================================================
# Node: Route by Objective State
# =============================================================================

def route_by_objective_state(state: TutorGraphContext) -> Literal["tutor_turn_placeholder", "lesson_complete", "select_current_objective"]:
    """
    Router node that decides the next node based on current objective state.
    
    Returns:
        - "lesson_complete" if all objectives are terminal
        - "select_current_objective" if current objective just became terminal and there are more
        - "tutor_turn_placeholder" for active teaching states
    """
    if not state.current_objective_id:
        # No current objective means all are done
        return "lesson_complete"
    
    current_obj_state = state.objectives.get(state.current_objective_id)
    if not current_obj_state:
        logger.warning(f"Current objective {state.current_objective_id} not found in objectives dict")
        return "lesson_complete"
    
    obj_state = ObjectiveTeachingState(current_obj_state.state)
    
    # Check if terminal
    if obj_state in [ObjectiveTeachingState.MASTERED, ObjectiveTeachingState.ESCALATE]:
        # Check if there are remaining non-terminal objectives
        has_remaining = any(
            ObjectiveTeachingState(obj.state) not in [ObjectiveTeachingState.MASTERED, ObjectiveTeachingState.ESCALATE]
            for obj in state.objectives.values()
        )
        
        if has_remaining:
            logger.info(f"Objective {state.current_objective_id} is terminal ({obj_state}), selecting next objective")
            return "select_current_objective"
        else:
            logger.info("All objectives are terminal, completing lesson")
            return "lesson_complete"
    
    # Active teaching state - continue with turn
    return "tutor_turn_placeholder"


# =============================================================================
# Node: Tutor Turn Placeholder (STUB)
# =============================================================================

async def tutor_turn_placeholder(
    state: TutorGraphContext
) -> TutorGraphContext:
    """
    STUB node for tutor turn logic.
    
    In M4-C, this is a placeholder that:
    - Sets a dummy tutor reply
    - Increments questions_asked
    - Builds a fake performance snapshot (always correct)
    - Calls apply_objective_state_transition to exercise state machine
    
    In later stories (M4-D+), this will be replaced by the full thinking loop.
    """
    if not state.current_objective_id:
        state.tutor_reply = "No current objective selected."
        return state
    
    current_obj_state = state.objectives[state.current_objective_id]
    
    # Increment questions counter
    current_obj_state.questions_asked += 1
    current_obj_state.questions_correct += 1  # Fake: always correct for stub
    
    # Build fake performance snapshot (stub logic)
    performance = ObjectivePerformanceSnapshot(
        total_attempts=current_obj_state.questions_asked,
        correct_attempts=current_obj_state.questions_correct,
        incorrect_attempts=current_obj_state.questions_incorrect,
        recent_answers=[{"correct": True} for _ in range(current_obj_state.questions_asked)]
    )
    
    # Apply state transition
    objective_repo = ObjectiveStateRepository(state.db_session)
    
    args = ApplyObjectiveTransitionArgs(
        tenant_id=state.tenant_id,
        session_id=state.session.id,
        objective_id=state.current_objective_id,
        performance=performance,
        objective_config=state.objective_config
    )
    
    updated_model = await apply_objective_state_transition(
        repo=objective_repo,
        args=args
    )
    
    await state.db_session.commit()
    
    # Reflect updated state back into in-memory context
    current_obj_state.state = updated_model.state
    current_obj_state.mastery_estimate = updated_model.mastery_estimate
    current_obj_state.questions_asked = updated_model.questions_asked
    current_obj_state.questions_correct = updated_model.questions_correct
    current_obj_state.questions_incorrect = updated_model.questions_incorrect
    
    # Set dummy tutor reply
    state.tutor_reply = (
        f"[STUB] Tutor placeholder for objective '{state.current_objective_id}'. "
        f"State: {updated_model.state}, Mastery: {updated_model.mastery_estimate}. "
        f"Questions: {updated_model.questions_asked}/{len(state.objective_ids)}. "
        f"Implementation pending in M4-D+."
    )
    
    logger.info(f"Stub turn completed. Objective {state.current_objective_id} state: {updated_model.state}")
    
    return state


# =============================================================================
# Node: Lesson Complete
# =============================================================================

async def lesson_complete(state: TutorGraphContext) -> TutorGraphContext:
    """
    Handles lesson completion.
    
    Sets lesson_complete flag and provides a final message.
    """
    state.lesson_complete = True
    
    if not state.tutor_reply:
        mastered_count = sum(
            1 for obj in state.objectives.values()
            if obj.state == ObjectiveTeachingState.MASTERED.value
        )
        escalated_count = sum(
            1 for obj in state.objectives.values()
            if obj.state == ObjectiveTeachingState.ESCALATE.value
        )
        total = mastered_count + escalated_count

        if escalated_count == 0:
            state.tutor_reply = (
                f"Great job! You've completed this lesson and mastered all "
                f"{mastered_count} objective{'s' if mastered_count != 1 else ''}. "
                f"Keep up the fantastic work!"
            )
        elif mastered_count == 0:
            state.tutor_reply = (
                f"We've finished this lesson. It looks like you found "
                f"{'these topics' if escalated_count > 1 else 'this topic'} "
                f"challenging — that's completely okay! Your teacher will "
                f"review and help you with the areas that need extra practice."
            )
        else:
            state.tutor_reply = (
                f"Lesson complete! You mastered {mastered_count} out of "
                f"{total} objectives — well done! Your teacher will help "
                f"you with the remaining {'ones' if escalated_count > 1 else 'one'}."
            )
    
    logger.info(f"Lesson {state.lesson_id} completed for session {state.session_id}")
    
    return state


# =============================================================================
# Node: Save Session and Profile
# =============================================================================

async def save_session_and_profile(
    state: TutorGraphContext
) -> TutorGraphContext:
    """
    Persist updated models back to the database.
    
    Updates:
    - TutorSession (current_objective_id, status, ended_at if complete)
    - All ObjectiveState records (already saved by apply_objective_state_transition)
    - StudentProfile aggregates (if needed)
    """
    session_repo = TutorSessionRepository(state.db_session)
    
    # Update TutorSession
    update_data = {
        "current_objective_id": state.current_objective_id,
    }
    
    # Set started_at on first turn
    if state.is_new_session and not state.session.started_at:
        update_data["started_at"] = datetime.utcnow()
    
    # Set status and ended_at if lesson complete
    if state.lesson_complete:
        update_data["status"] = TutorSessionStatus.COMPLETED
        update_data["ended_at"] = datetime.utcnow()
    
    # Save session metadata: last_tutor_message, chat_history, no_answer_streak
    current_metadata = state.session.session_metadata or {}
    if state.tutor_reply:
        current_metadata["last_tutor_message"] = state.tutor_reply
    
    # Append to chat history (student message then tutor reply)
    chat_history = current_metadata.get("chat_history", [])
    if state.student_message:
        chat_history.append({"role": "student", "content": state.student_message})
    if state.tutor_reply:
        chat_history.append({"role": "assistant", "content": state.tutor_reply})
    
    # Trim history to last N messages (configurable)
    max_messages = DEFAULT_TUTOR_BEHAVIOR_CONFIG.chat_history_max_messages
    if len(chat_history) > max_messages:
        chat_history = chat_history[-max_messages:]
    current_metadata["chat_history"] = chat_history
    current_metadata["no_answer_streak"] = state.no_answer_streak
    current_metadata["objective_labels"] = state.objective_labels or current_metadata.get("objective_labels", {})
    
    update_data["session_metadata"] = current_metadata
    
    await session_repo.update_session(
        tenant_id=state.tenant_id,
        session_id=state.session.id,
        **update_data
    )
    
    await state.db_session.commit()
    
    logger.info(f"Saved session {state.session_id} with current_objective={state.current_objective_id}")
    
    # TODO: Update StudentProfile aggregates (future enhancement)
    
    return state

