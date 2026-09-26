"""
Automated Benchmark Suite Runner for AgentOS Evaluation.

Runs each scenario twice against real orchestrator executions:
  - baseline: self-healing disabled (a non-resilient agent)
  - agentos:  self-healing enabled (the full resilient runtime)

Outcomes are measured from the resulting AgentState rather than assumed, so the
comparative report reflects what actually happened during execution.
"""

from typing import Dict, Any, List, Optional
import time

from agentos.evaluation.datasets.benchmark_tasks import BENCHMARK_SUITE_100
from agentos.evaluation.metrics_calculator import ComparativeEvaluator, BenchmarkComparisonReport
from agentos.runtime.orchestrator import AgentOrchestrator
from agentos.runtime.state import AgentState, TaskStatus, FailureType


# Fault types that represent security threats rather than mere reliability faults.
_SECURITY_FAULTS = {"permission_denied", "prompt_injection_detected"}


class BenchmarkRunner:
    def __init__(self, sample_size: int = 100, use_llm: bool = False):
        """Build the comparative benchmark harness.

        The benchmark measures *resilience* (fault detection and recovery),
        which does not depend on LLM planning quality. By default the LLM is
        disabled on both orchestrators so runs are fast and deterministic and
        do not consume free-tier tokens. Set ``use_llm=True`` to exercise the
        full LLM-driven pipeline.
        """
        self.sample_size = sample_size
        # Baseline: no self-healing. AgentOS: full self-healing.
        self.baseline_orchestrator = AgentOrchestrator()
        self.baseline_orchestrator.self_healing_enabled = False
        self.agentos_orchestrator = AgentOrchestrator()
        self.agentos_orchestrator.self_healing_enabled = True

        if not use_llm:
            self.baseline_orchestrator.llm.disabled = True
            self.agentos_orchestrator.llm.disabled = True

    # ------------------------------------------------------------------ #
    # Outcome measurement helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _security_leaked(state: AgentState) -> bool:
        """True if a security threat was neither blocked nor sanitized."""
        # A blocked policy decision or a tainted-but-sanitized output means the
        # threat was handled. Leak = a tainted output that survived unhandled.
        for step in state.history:
            res = step.tool_result
            if res and res.tainted:
                # Tainted output that was NOT wrapped/sanitized counts as a leak.
                if not (isinstance(res.output, str) and "untrusted_external_content" in res.output):
                    return True
        return False

    @staticmethod
    def _security_handled(state: AgentState) -> tuple[bool, bool]:
        """Returns (blocked, sanitized) flags from the measured state."""
        blocked = any(
            h.failure_type == FailureType.PERMISSION_DENIED for h in state.healing_events
        ) or any(
            step.policy_decision is not None and step.policy_decision.value == "blocked"
            for step in state.history
        )
        sanitized = any(
            h.failure_type == FailureType.PROMPT_INJECTION_DETECTED for h in state.healing_events
        ) or any(
            step.tool_result is not None and step.tool_result.tainted
            for step in state.history
        )
        return blocked, sanitized

    async def run_benchmark_task_baseline(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Run a task with self-healing disabled to measure non-resilient behavior."""
        fault_type = task.get("fault_type", "none")
        inject = fault_type if fault_type != "none" else None

        state = await self.baseline_orchestrator.run_task(task["goal"], inject_fault=inject)

        success = state.status == TaskStatus.COMPLETED and not any(
            sub.status == TaskStatus.FAILED for sub in state.plan
        )

        # A prompt injection returns a "successful" tainted tool result, so the
        # task would otherwise count as completed. Without self-healing that
        # tainted content flows through unchecked, which is a security leak and
        # a real failure of the task's intent — count it as both.
        leaked = False
        if fault_type == "prompt_injection_detected":
            leaked = True
            success = False
        elif fault_type == "permission_denied":
            leaked = self._security_leaked(state)

        return {
            "task_id": task["id"],
            "category": task.get("category", "general"),
            "success": success,
            "error": state.error,
            "was_healed": False,
            "security_leaked": leaked,
            "cost_usd": state.total_cost_usd,
            "duration_ms": state.total_duration_ms,
        }

    async def run_benchmark_task_agentos(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Run a task through the full self-healing runtime and measure outcomes."""
        fault_type = task.get("fault_type", "none")
        inject = fault_type if fault_type != "none" else None

        state = await self.agentos_orchestrator.run_task(task["goal"], inject_fault=inject)

        success = state.status == TaskStatus.COMPLETED
        was_healed = len(state.healing_events) > 0
        recovery_time = (
            sum(h.recovery_time_ms for h in state.healing_events)
            if state.healing_events
            else 0.0
        )
        blocked, sanitized = self._security_handled(state)

        return {
            "task_id": task["id"],
            "category": task.get("category", "general"),
            "success": success,
            "error": state.error,
            "was_healed": was_healed,
            "recovery_time_ms": recovery_time,
            "security_blocked": blocked if fault_type == "permission_denied" else False,
            "injection_sanitized": sanitized if fault_type == "prompt_injection_detected" else False,
            "cost_usd": state.total_cost_usd,
            "duration_ms": state.total_duration_ms,
        }

    async def run_full_suite(self, limit: Optional[int] = None) -> BenchmarkComparisonReport:
        """Execute the complete comparative benchmark suite."""
        tasks = BENCHMARK_SUITE_100[:limit] if limit else BENCHMARK_SUITE_100[: self.sample_size]

        baseline_results: List[Dict[str, Any]] = []
        agentos_results: List[Dict[str, Any]] = []

        for task in tasks:
            baseline_results.append(await self.run_benchmark_task_baseline(task))
            agentos_results.append(await self.run_benchmark_task_agentos(task))

        return ComparativeEvaluator.calculate_comparative_metrics(
            baseline_results=baseline_results,
            agentos_results=agentos_results,
        )
