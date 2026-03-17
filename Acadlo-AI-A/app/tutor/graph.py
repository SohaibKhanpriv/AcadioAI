"""
LangGraph Tutor graph definition.

This module builds and compiles the tutor graph using LangGraph.

The thinking loop is:
- node_analyze_student_turn
- node_update_performance_and_state
- node_evaluate_progress (NEW)
- node_plan_tutor_action
- node_generate_tutor_response
"""
import logging
from typing import Literal
from langgraph.graph import StateGraph, END

from app.tutor.graph_context import TutorGraphContext
from app.tutor.graph_nodes import (
    load_session_and_profile,
    onboarding_check,
    generate_onboarding_response,
    resolve_lesson,
    select_current_objective,
    route_by_objective_state,
    lesson_complete,
    save_session_and_profile,
)
from app.tutor.thinking_loop_nodes import (
    node_analyze_student_turn,
    node_update_performance_and_state,
    node_evaluate_progress,
    node_plan_tutor_action,
    node_generate_tutor_response,
)

logger = logging.getLogger(__name__)


def build_tutor_graph():
    """
    Build and compile the Tutor LangGraph.
    
    The graph implements the full thinking loop:
    1. Load session and profile
    2. Select current objective
    3. Route based on objective state:
       - If active: run thinking loop (analyze → update → evaluate → plan → generate)
       - If all terminal: complete lesson
    4. Save session and profile
    """
    graph = StateGraph(TutorGraphContext)
    
    # Add session/profile nodes
    graph.add_node("load_session_and_profile", load_session_and_profile)
    graph.add_node("onboarding_check", onboarding_check)
    graph.add_node("generate_onboarding_response", generate_onboarding_response)
    graph.add_node("resolve_lesson", resolve_lesson)
    graph.add_node("select_current_objective", select_current_objective)
    graph.add_node("lesson_complete", lesson_complete)
    graph.add_node("save_session_and_profile", save_session_and_profile)
    
    # Add thinking loop nodes
    graph.add_node("analyze_student_turn", node_analyze_student_turn)
    graph.add_node("update_performance_and_state", node_update_performance_and_state)
    graph.add_node("evaluate_progress", node_evaluate_progress)
    graph.add_node("plan_tutor_action", node_plan_tutor_action)
    graph.add_node("generate_tutor_response", node_generate_tutor_response)
    
    # Set entry point
    graph.set_entry_point("load_session_and_profile")
    
    # Onboarding: after load, check if we need to ask questions
    graph.add_edge("load_session_and_profile", "onboarding_check")
    graph.add_conditional_edges(
        "onboarding_check",
        _route_after_onboarding,
        {
            "generate_onboarding_response": "generate_onboarding_response",
            "resolve_lesson": "resolve_lesson",
        },
    )
    graph.add_edge("generate_onboarding_response", "save_session_and_profile")
    graph.add_edge("resolve_lesson", "select_current_objective")
    
    # Conditional routing from select_current_objective
    graph.add_conditional_edges(
        "select_current_objective",
        route_by_objective_state_updated,
        {
            "thinking_loop": "analyze_student_turn",
            "lesson_complete": "lesson_complete",
            "select_current_objective": "select_current_objective",
        }
    )
    
    # Thinking loop edges (sequential: analyze → update → evaluate → plan → generate)
    graph.add_edge("analyze_student_turn", "update_performance_and_state")
    graph.add_edge("update_performance_and_state", "evaluate_progress")
    graph.add_edge("evaluate_progress", "plan_tutor_action")
    graph.add_edge("plan_tutor_action", "generate_tutor_response")
    
    # After response generation, go to save
    graph.add_edge("generate_tutor_response", "save_session_and_profile")
    
    # Lesson complete also goes to save
    graph.add_edge("lesson_complete", "save_session_and_profile")
    
    # After save, end
    graph.add_edge("save_session_and_profile", END)
    
    logger.info(
        "Built tutor graph with thinking loop: "
        "load → select → (analyze → update → evaluate → plan → generate) → save"
    )
    
    return graph.compile()


def _route_after_onboarding(
    state: TutorGraphContext,
) -> Literal["generate_onboarding_response", "resolve_lesson"]:
    """Route after onboarding_check: ask more questions or proceed to resolve_lesson."""
    complete = (
        state.get("onboarding_complete", False)
        if isinstance(state, dict)
        else getattr(state, "onboarding_complete", False)
    )
    if complete:
        return "resolve_lesson"
    return "generate_onboarding_response"


def route_by_objective_state_updated(
    state: TutorGraphContext
) -> Literal["thinking_loop", "lesson_complete", "select_current_objective"]:
    """
    Router node that decides the next node based on current objective state.
    """
    from app.tutor.enums import ObjectiveTeachingState
    
    if not state.current_objective_id:
        return "lesson_complete"
    
    current_obj_state = state.objectives.get(state.current_objective_id)
    if not current_obj_state:
        logger.warning(f"Current objective {state.current_objective_id} not found in objectives dict")
        return "lesson_complete"
    
    obj_state = ObjectiveTeachingState(current_obj_state.state)
    
    if obj_state in [ObjectiveTeachingState.MASTERED, ObjectiveTeachingState.ESCALATE]:
        has_remaining = any(
            ObjectiveTeachingState(obj.state) not in [
                ObjectiveTeachingState.MASTERED, 
                ObjectiveTeachingState.ESCALATE
            ]
            for obj in state.objectives.values()
        )
        
        if has_remaining:
            logger.info(f"Objective {state.current_objective_id} is terminal ({obj_state}), selecting next")
            return "select_current_objective"
        else:
            logger.info("All objectives are terminal, completing lesson")
            return "lesson_complete"
    
    return "thinking_loop"


# Global compiled graph instance
tutor_app = build_tutor_graph()
