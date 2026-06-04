"""LangGraph workflow assembly + run/resume entrypoints.

Workflow shape::

    parse_task -> retrieve_crm_context -> retrieve_vector_context
      -> analyze_risks -> detect_missing_fields -> recommend_next_steps
      -> draft_crm_update -> approval_router --(conditional)-->
            * pending    -> END (persist; wait for human)
            * writeback  -> writeback_crm -> finalize_report -> END
            * finalize   -> finalize_report -> END

Human-in-the-loop / resumability is implemented with our own durable persistence
(`agent_tasks.state`) rather than an in-memory checkpointer, so a pending task
survives process restarts. On approval we run a small resume graph
(writeback_crm -> finalize_report). On rejection we stop without writeback.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.instrumentation import instrument_node
from app.agents.nodes import make_nodes
from app.agents.routers import route_after_approval
from app.agents.state import AgentState, initial_state
from app.db.models import AgentTask
from app.services.agent_task_service import AgentTaskService
from app.utils.logging import get_logger

logger = get_logger(__name__)


def build_review_graph(session: Session):
    """Compile the main opportunity-review graph (up to approval routing)."""
    nodes = make_nodes(session)
    g = StateGraph(AgentState)

    for name in [
        "parse_task",
        "retrieve_crm_context",
        "retrieve_vector_context",
        "analyze_risks",
        "detect_missing_fields",
        "recommend_next_steps",
        "draft_crm_update",
        "approval_router",
        "writeback_crm",
        "finalize_report",
    ]:
        g.add_node(name, instrument_node(session, name, nodes[name]))

    g.add_edge(START, "parse_task")
    g.add_edge("parse_task", "retrieve_crm_context")
    g.add_edge("retrieve_crm_context", "retrieve_vector_context")
    g.add_edge("retrieve_vector_context", "analyze_risks")
    g.add_edge("analyze_risks", "detect_missing_fields")
    g.add_edge("detect_missing_fields", "recommend_next_steps")
    g.add_edge("recommend_next_steps", "draft_crm_update")
    g.add_edge("draft_crm_update", "approval_router")

    g.add_conditional_edges(
        "approval_router",
        route_after_approval,
        {"pending": END, "writeback": "writeback_crm", "finalize": "finalize_report"},
    )
    g.add_edge("writeback_crm", "finalize_report")
    g.add_edge("finalize_report", END)
    return g.compile()


def build_resume_graph(session: Session):
    """Compile the post-approval resume graph: writeback -> finalize."""
    nodes = make_nodes(session)
    g = StateGraph(AgentState)
    g.add_node("writeback_crm", instrument_node(session, "writeback_crm", nodes["writeback_crm"]))
    g.add_node("finalize_report", instrument_node(session, "finalize_report", nodes["finalize_report"]))
    g.add_edge(START, "writeback_crm")
    g.add_edge("writeback_crm", "finalize_report")
    g.add_edge("finalize_report", END)
    return g.compile()


def _execute_review(session: Session, task: AgentTask) -> dict:
    """Run the review graph for an existing task, persist, and return state."""
    tasks = AgentTaskService(session)
    state = initial_state(task.task_id, task.opportunity_id, task.user_task)
    graph = build_review_graph(session)
    final_state = graph.invoke(state)

    if final_state.get("approval_status") == "pending":
        final_state["execution_status"] = "pending_approval"
    tasks.save_state(task, final_state)
    session.commit()
    return final_state


def run_review_workflow(session: Session, opportunity_id: str, user_task: str) -> dict:
    """Create a task, run the review graph synchronously, and return final state."""
    task = AgentTaskService(session).create_task(
        opportunity_id=opportunity_id, account_id=None, user_task=user_task
    )
    return _execute_review(session, task)


def create_queued_task(session: Session, opportunity_id: str, user_task: str) -> AgentTask:
    """Create a task in the 'queued' state for asynchronous execution."""
    tasks = AgentTaskService(session)
    task = tasks.create_task(
        opportunity_id=opportunity_id, account_id=None, user_task=user_task,
        execution_status="queued",
    )
    tasks.save_state(task, {
        "task_id": task.task_id,
        "opportunity_id": opportunity_id,
        "account_id": None,
        "user_task": user_task,
        "execution_status": "queued",
        "approval_status": "not_required",
        "requires_human_approval": False,
        "audit_log": [],
    })
    session.commit()
    return task


def run_review_task_in_background(task_id: str) -> None:
    """Background runner: opens its OWN session so it survives request teardown.

    Transitions: queued -> running -> completed | pending_approval | error.
    """
    from app.db.session import SessionLocal
    from app.services.crm_service import CRMService

    session = SessionLocal()
    try:
        tasks = AgentTaskService(session)
        task = tasks.get_task(task_id)
        if task is None:
            logger.warning("Background runner: task %s not found", task_id)
            return

        # queued -> running
        task.execution_status = "running"
        tasks.save_state(task, {**(task.state or {}), "execution_status": "running"})
        session.commit()

        # Validate the opportunity exists; otherwise terminate as 'error'.
        if CRMService(session).get_opportunity(task.opportunity_id) is None:
            message = f"Opportunity {task.opportunity_id} not found"
            tasks.write_audit(task_id, "async_runner", task.opportunity_id or "", message,
                              status="error", error_message=message)
            tasks.save_state(task, {
                **(task.state or {}),
                "execution_status": "error",
                "approval_status": "not_required",
                "error": message,
            })
            session.commit()
            return

        _execute_review(session, task)
    except Exception as exc:  # pragma: no cover - defensive; surfaced as 'error'
        logger.exception("Background review failed for task %s", task_id)
        try:
            tasks = AgentTaskService(session)
            task = tasks.get_task(task_id)
            if task is not None:
                tasks.save_state(task, {
                    **(task.state or {}),
                    "execution_status": "error",
                    "error": str(exc),
                })
                session.commit()
        except Exception:
            logger.exception("Failed to record error state for task %s", task_id)
    finally:
        session.close()


def resume_after_approval(session: Session, task: AgentTask, state: dict) -> dict:
    """Resume an approved task: run writeback + finalize, persist, return state."""
    tasks = AgentTaskService(session)
    graph = build_resume_graph(session)
    final_state = graph.invoke(state)
    final_state["approval_status"] = "approved"
    final_state["execution_status"] = "completed"
    tasks.save_state(task, final_state)
    session.commit()
    return final_state
