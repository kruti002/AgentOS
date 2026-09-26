"""
Live-LLM quality evaluation harness.

Distinct from the resilience benchmark (which injects faults with the LLM
disabled), this harness runs a small set of tasks with *known correct answers*
through the full LLM-driven pipeline and scores whether the agent's final
output actually contains the expected facts.

It is opt-in and requires a reachable LLM endpoint; when the LLM is unavailable
each case is reported as skipped rather than failed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import re

from pydantic import BaseModel, Field

from agentos.runtime.orchestrator import AgentOrchestrator
from agentos.runtime.state import TaskStatus


class QualityCase(BaseModel):
    id: str
    goal: str
    # All of these substrings (case-insensitive) must appear in the final output.
    expected_all: List[str] = Field(default_factory=list)
    # At least one of these must appear (optional).
    expected_any: List[str] = Field(default_factory=list)


class QualityCaseResult(BaseModel):
    id: str
    goal: str
    status: str            # "completed" / "failed" / "skipped"
    passed: bool
    matched: List[str]
    missing: List[str]
    tokens: int = 0
    cost_usd: float = 0.0
    final_output: str = ""


class QualityReport(BaseModel):
    total_cases: int
    scored_cases: int
    skipped_cases: int
    passed: int
    pass_rate_pct: float
    total_tokens: int
    total_cost_usd: float
    results: List[QualityCaseResult]


# Known-answer cases grounded in the seeded DuckDB `system_metrics` table.
# Seeded rows: api-gateway(18.2,HEALTHY), auth-service(9.4,HEALTHY),
# agent-runtime(142.6,DEGRADED), mcp-broker(4.1,HEALTHY), db-cluster(45.8,HEALTHY).
DEFAULT_QUALITY_CASES: List[QualityCase] = [
    QualityCase(
        id="Q-DB-HIGHEST-LATENCY",
        goal="Query the system_metrics table and report the single service with the highest latency_ms.",
        expected_all=["agent-runtime"],
        expected_any=["142.6", "142"],
    ),
    QualityCase(
        id="Q-DB-DEGRADED",
        goal="Query the system_metrics table and report which service has status DEGRADED.",
        expected_all=["agent-runtime"],
    ),
    QualityCase(
        id="Q-CALC",
        goal="Compute the value of sqrt(144) + 10 * 2 using the calculator tool and report the numeric result.",
        expected_any=["32"],
    ),
]


class QualityEvaluator:
    def __init__(self, orchestrator: Optional[AgentOrchestrator] = None):
        # Full LLM-driven pipeline (LLM must be reachable).
        self.orchestrator = orchestrator or AgentOrchestrator()

    async def run_case(self, case: QualityCase) -> QualityCaseResult:
        if not self.orchestrator.llm.available:
            return QualityCaseResult(
                id=case.id, goal=case.goal, status="skipped",
                passed=False, matched=[], missing=case.expected_all,
            )

        state = await self.orchestrator.run_task(case.goal)
        output = (state.final_output or "").lower()

        matched: List[str] = []
        missing: List[str] = []
        for term in case.expected_all:
            (matched if term.lower() in output else missing).append(term)

        all_ok = len(missing) == 0
        any_ok = True
        if case.expected_any:
            any_hits = [t for t in case.expected_any if t.lower() in output]
            matched.extend(any_hits)
            any_ok = len(any_hits) > 0
            if not any_ok:
                missing.append("|".join(case.expected_any))

        return QualityCaseResult(
            id=case.id,
            goal=case.goal,
            status=state.status.value if hasattr(state.status, "value") else str(state.status),
            passed=(state.status == TaskStatus.COMPLETED and all_ok and any_ok),
            matched=matched,
            missing=missing,
            tokens=state.total_tokens,
            cost_usd=state.total_cost_usd,
            final_output=(state.final_output or "")[:4000],
        )

    async def run(self, cases: Optional[List[QualityCase]] = None) -> QualityReport:
        cases = cases or DEFAULT_QUALITY_CASES
        results = [await self.run_case(c) for c in cases]

        scored = [r for r in results if r.status != "skipped"]
        passed = sum(1 for r in scored if r.passed)
        pass_rate = (passed / len(scored) * 100.0) if scored else 0.0

        return QualityReport(
            total_cases=len(results),
            scored_cases=len(scored),
            skipped_cases=len(results) - len(scored),
            passed=passed,
            pass_rate_pct=round(pass_rate, 1),
            total_tokens=sum(r.tokens for r in results),
            total_cost_usd=round(sum(r.cost_usd for r in results), 6),
            results=results,
        )
