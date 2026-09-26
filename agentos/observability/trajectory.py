"""
Real-time trajectory event publisher and stream distributor for SSE/WebSockets.
"""

from typing import Dict, Any, List, Optional, Callable, AsyncGenerator
import asyncio
import json
import time
from pydantic import BaseModel, Field


class TrajectoryEvent(BaseModel):
    event_id: str
    task_id: str
    event_type: str  # "STEP_START", "THOUGHT", "TOOL_CALL", "TOOL_RESULT", "HEALING", "SECURITY", "COMPLETED", "FAILED"
    payload: Dict[str, Any]
    timestamp: float = Field(default_factory=time.time)


class TrajectoryPublisher:
    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._history: Dict[str, List[TrajectoryEvent]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """Subscribe to live events for a specific task."""
        queue: asyncio.Queue = asyncio.Queue()
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        self._subscribers[task_id].append(queue)
        
        # If there is existing history for this task, replay it into queue
        if task_id in self._history:
            for past_event in self._history[task_id]:
                queue.put_nowait(past_event)
                
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        if task_id in self._subscribers and queue in self._subscribers[task_id]:
            self._subscribers[task_id].remove(queue)

    def publish(self, event: TrajectoryEvent) -> None:
        """Broadcast event to all task subscribers."""
        task_id = event.task_id
        if task_id not in self._history:
            self._history[task_id] = []
        self._history[task_id].append(event)

        if task_id in self._subscribers:
            for queue in self._subscribers[task_id]:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    async def event_generator(self, task_id: str) -> AsyncGenerator[str, None]:
        """Yield event payloads for SSE.

        Yields the raw JSON string only; the SSE framing (the ``data:`` prefix
        and blank-line separator) is added by the EventSourceResponse wrapper.
        Emitting our own ``data:`` here would double-prefix each event and break
        the browser's EventSource parser.
        """
        queue = self.subscribe(task_id)
        try:
            while True:
                event = await queue.get()
                yield event.model_dump_json()
                if event.event_type in ("COMPLETED", "FAILED", "CANCELLED"):
                    break
        finally:
            self.unsubscribe(task_id, queue)


# Global publisher bus
trajectory_bus = TrajectoryPublisher()
