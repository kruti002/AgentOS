"""
Agent task execution, approval, and state endpoints.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import uuid
from agentos.runtime.orchestrator import global_orchestrator
from agentos.runtime.state import AgentState, TaskStatus
from agentos.storage import global_store

router = APIRouter(prefix="/api/agent", tags=["Agent"])


class RunTaskRequest(BaseModel):
    goal: str
    model_name: Optional[str] = "gemini-2.5-flash"
    task_id: Optional[str] = None


class RunTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class ApprovalRequest(BaseModel):
    task_id: str
    approval_id: str
    approved: bool


@router.post("/run", response_model=RunTaskResponse)
async def run_agent_task(req: RunTaskRequest, bg_tasks: BackgroundTasks):
    """Dispatch an agent task asynchronously."""
    task_id = req.task_id or f"task_{uuid.uuid4().hex[:8]}"
    
    # Run in background task
    bg_tasks.add_task(global_orchestrator.run_task, req.goal, task_id)
    
    return RunTaskResponse(
        task_id=task_id,
        status="running",
        message="Task dispatched to AgentOS runtime orchestrator."
    )


@router.post("/delegate")
async def delegate_task(req: RunTaskRequest):
    """Run a goal through the multi-agent coordinator (parallel sub-agents)."""
    from agentos.runtime.coordinator import AgentCoordinator

    report = await AgentCoordinator().run(req.goal)
    return report.model_dump()


@router.post("/approve")
async def approve_pending(req: ApprovalRequest):
    """Approve or deny a pending human-in-the-loop tool call."""
    ok = global_orchestrator.resolve_approval(req.approval_id, req.approved)
    if not ok:
        raise HTTPException(status_code=404, detail=f"No pending approval '{req.approval_id}'.")
    return {"approval_id": req.approval_id, "approved": req.approved, "status": "resolved"}


@router.post("/cancel/{task_id}")
async def cancel_task(task_id: str):
    """Request cancellation of a running task."""
    ok = global_orchestrator.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not active or already finished.")
    return {"task_id": task_id, "status": "cancelling"}


@router.get("/state/{task_id}")
async def get_task_state(task_id: str):
    """Retrieve full execution state and history for a given task."""
    state = global_orchestrator.get_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return state.model_dump()


@router.get("/tasks")
async def list_recent_tasks():
    """List recent tasks in the runtime."""
    return [
        {
            "task_id": s.task_id,
            "goal": s.goal,
            "status": s.status.value,
            "current_step": s.current_step,
            "total_tokens": s.total_tokens,
            "cost_usd": s.total_cost_usd,
            "duration_ms": s.total_duration_ms,
            "healing_count": len(s.healing_events)
        }
        for s in global_orchestrator._active_tasks.values()
    ]


@router.get("/history")
async def list_persisted_history(limit: int = 50):
    """List durable task history from persistent storage (survives restarts)."""
    return {
        "summary": global_store.history_summary(),
        "tasks": global_store.list_tasks(limit=limit),
    }


@router.get("/history/{task_id}")
async def get_persisted_task(task_id: str):
    """Fetch a single persisted task record."""
    rec = global_store.get_task(task_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"No persisted task '{task_id}'.")
    return rec
