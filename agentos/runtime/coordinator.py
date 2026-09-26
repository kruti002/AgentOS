"""
Multi-agent coordinator.

Decomposes a complex goal into independent sub-goals, runs each through its own
AgentOrchestrator (each with a fresh AgentState), then synthesizes a single
merged answer. Sub-agents run concurrently. Falls back to a single-agent run
when the LLM is unavailable or decomposition yields one sub-goal.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import asyncio
import uuid

from pydantic import BaseModel, Field

from agentos.runtime.orchestrator import AgentOrchestrator
from agentos.runtime.state import AgentState, TaskStatus
from agentos.llm.client import LLMClient, LLMUnavailable, global_llm
from agentos.observability.trajectory import trajectory_bus, TrajectoryEvent


DECOMPOSE_PROMPT = """You are a multi-agent coordinator. Split the user's goal
into 2-4 INDEPENDENT sub-goals that can be worked on in parallel by separate
agents. If the goal is simple and not worth splitting, return a single sub-goal.

Respond with ONLY JSON: {"subgoals": ["...", "..."]}"""


class SubAgentResult(BaseModel):
    sub_goal: str
    task_id: str
    status: str
    output: str
    tokens: int = 0
    cost_usd: float = 0.0


class CoordinatorReport(BaseModel):
    coordinator_task_id: str
    goal: str
    sub_goals: List[str]
    sub_results: List[SubAgentResult]
    final_output: str
    total_tokens: int
    total_cost_usd: float


class AgentCoordinator:
    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or global_llm

    async def run(self, goal: str) -> CoordinatorReport:
        coord_id = f"coord_{uuid.uuid4().hex[:8]}"
        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=coord_id, event_type="COORDINATOR_START",
            payload={"goal": goal},
        ))

        sub_goals = self._decompose(goal)
        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=coord_id, event_type="COORDINATOR_PLAN",
            payload={"sub_goals": sub_goals},
        ))

        # Run each sub-goal through its own orchestrator (fresh AgentState).
        # The underlying LLM client is synchronous, so sub-agents run
        # sequentially; each keeps its own isolated state and history.
        async def run_sub(sub_goal: str) -> SubAgentResult:
            orch = AgentOrchestrator(llm=self.llm)
            state: AgentState = await orch.run_task(sub_goal, task_id=f"{coord_id}_{uuid.uuid4().hex[:4]}")
            return SubAgentResult(
                sub_goal=sub_goal,
                task_id=state.task_id,
                status=state.status.value if hasattr(state.status, "value") else str(state.status),
                output=(state.final_output or "")[:4000],
                tokens=state.total_tokens,
                cost_usd=state.total_cost_usd,
            )

        sub_results: List[SubAgentResult] = []
        for sg in sub_goals:
            sub_results.append(await run_sub(sg))

        final_output = self._merge(goal, sub_results)
        total_tokens = sum(r.tokens for r in sub_results)
        total_cost = round(sum(r.cost_usd for r in sub_results), 6)

        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=coord_id, event_type="COORDINATOR_COMPLETED",
            payload={"final_output": final_output, "total_tokens": total_tokens},
        ))

        return CoordinatorReport(
            coordinator_task_id=coord_id,
            goal=goal,
            sub_goals=sub_goals,
            sub_results=list(sub_results),
            final_output=final_output,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
        )

    def _decompose(self, goal: str) -> List[str]:
        """Split the goal into sub-goals via the LLM; fall back to a single goal."""
        if not self.llm.available:
            return [goal]
        try:
            parsed, _ = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": DECOMPOSE_PROMPT},
                    {"role": "user", "content": goal},
                ],
                temperature=0.2,
                max_tokens=400,
            )
        except LLMUnavailable:
            return [goal]

        if isinstance(parsed, dict):
            subs = parsed.get("subgoals") or parsed.get("sub_goals")
            if isinstance(subs, list):
                cleaned = [str(s).strip() for s in subs if str(s).strip()]
                if cleaned:
                    return cleaned[:4]
        return [goal]

    def _merge(self, goal: str, results: List[SubAgentResult]) -> str:
        """Synthesize sub-agent outputs into one answer."""
        blocks = "\n\n".join(f"### Sub-goal: {r.sub_goal}\n{r.output}" for r in results)
        if not self.llm.available:
            return f"# Combined Result for: {goal}\n\n{blocks}"

        prompt = (
            "Merge the following sub-agent results into a single coherent answer "
            "for the overall goal. Use only the information provided.\n\n"
            f"Overall goal: {goal}\n\n{blocks}"
        )
        try:
            resp = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
            )
            return (resp.content or "").strip() or f"# Combined Result\n\n{blocks}"
        except LLMUnavailable:
            return f"# Combined Result for: {goal}\n\n{blocks}"
