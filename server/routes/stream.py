"""
Real-time SSE event streaming route.
"""

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from agentos.observability.trajectory import trajectory_bus

router = APIRouter(prefix="/api/stream", tags=["Streaming"])


@router.get("/{task_id}")
async def stream_task_events(task_id: str):
    """Server-Sent Events (SSE) stream for real-time trajectory events."""
    return EventSourceResponse(trajectory_bus.event_generator(task_id))
