"""
Observability, OpenTelemetry traces, and system metrics endpoints.
"""

from fastapi import APIRouter
from agentos.observability.tracer import global_tracer
from agentos.observability.metrics import global_metrics

router = APIRouter(prefix="/api/observability", tags=["Observability"])


@router.get("/metrics")
async def get_system_metrics():
    """Retrieve aggregate telemetry and cost metrics."""
    return global_metrics.get_summary().model_dump()


@router.get("/traces")
async def get_trace_tree():
    """Retrieve OpenTelemetry trace trees for visual waterfall rendering."""
    return {
        "spans": [s.model_dump() for s in global_tracer.recorded_spans],
        "tree": global_tracer.get_trace_tree()
    }


@router.get("/traces/{task_id}")
async def get_task_trace(task_id: str):
    """Return the trace span subtree for a single task (for UI correlation)."""
    return {"task_id": task_id, "tree": global_tracer.get_task_spans(task_id)}


@router.delete("/traces")
async def clear_traces():
    """Clear in-memory trace buffer."""
    global_tracer.clear()
    return {"status": "success", "message": "Trace buffer cleared."}
