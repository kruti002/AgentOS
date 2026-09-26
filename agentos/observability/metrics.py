"""
Token, cost, and runtime metrics collector for AgentOS.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import time
from agentos.config import settings


class CostCalculator:
    @staticmethod
    def calculate_cost(
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """Calculate USD cost based on token counts and model pricing."""
        rates = settings.cost_rates.get(model_name)
        if not rates:
            # Unknown or routed ("auto") model: use a configurable default rate
            # rather than an arbitrary named model's pricing.
            rates = getattr(settings, "default_cost_rate", None) or {"input": 0.10, "output": 0.30}

        cost_prompt = (prompt_tokens / 1_000_000.0) * rates["input"]
        cost_completion = (completion_tokens / 1_000_000.0) * rates["output"]
        return round(cost_prompt + cost_completion, 6)


class SystemMetricsSummary(BaseModel):
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    task_success_rate: float = 0.0
    total_failures_intercepted: int = 0
    total_failures_recovered: int = 0
    recovery_rate: float = 0.0
    mean_time_to_recovery_ms: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    security_violations_blocked: int = 0
    avg_latency_ms: float = 0.0


class MetricsCollector:
    def __init__(self):
        self.task_records: List[Dict[str, Any]] = []
        self.recovery_times: List[float] = []
        self.security_blocks: int = 0

    def record_task_completion(
        self,
        task_id: str,
        success: bool,
        duration_ms: float,
        tokens_used: int,
        cost_usd: float,
        failures_count: int,
        recovered_count: int
    ) -> None:
        """Record completed task metrics."""
        self.task_records.append({
            "task_id": task_id,
            "success": success,
            "duration_ms": duration_ms,
            "tokens_used": tokens_used,
            "cost_usd": cost_usd,
            "failures_count": failures_count,
            "recovered_count": recovered_count,
            "timestamp": time.time()
        })

    def record_recovery_event(self, recovery_time_ms: float) -> None:
        self.recovery_times.append(recovery_time_ms)

    def record_security_block(self) -> None:
        self.security_blocks += 1

    def get_summary(self) -> SystemMetricsSummary:
        """Compute aggregated system telemetry summary."""
        total_tasks = len(self.task_records)
        if total_tasks == 0:
            return SystemMetricsSummary(security_violations_blocked=self.security_blocks)

        success_tasks = sum(1 for t in self.task_records if t["success"])
        failed_tasks = total_tasks - success_tasks
        tsr = (success_tasks / total_tasks) * 100.0 if total_tasks > 0 else 0.0

        total_failures = sum(t["failures_count"] for t in self.task_records)
        total_recovered = sum(t["recovered_count"] for t in self.task_records)
        recovery_rate = (total_recovered / total_failures) * 100.0 if total_failures > 0 else 100.0

        mttr = (sum(self.recovery_times) / len(self.recovery_times)) if self.recovery_times else 0.0
        total_tokens = sum(t["tokens_used"] for t in self.task_records)
        total_cost = sum(t["cost_usd"] for t in self.task_records)
        avg_latency = sum(t["duration_ms"] for t in self.task_records) / total_tasks

        return SystemMetricsSummary(
            total_tasks=total_tasks,
            successful_tasks=success_tasks,
            failed_tasks=failed_tasks,
            task_success_rate=round(tsr, 2),
            total_failures_intercepted=total_failures,
            total_failures_recovered=total_recovered,
            recovery_rate=round(recovery_rate, 2),
            mean_time_to_recovery_ms=round(mttr, 2),
            total_tokens=total_tokens,
            total_cost_usd=round(total_cost, 6),
            security_violations_blocked=self.security_blocks,
            avg_latency_ms=round(avg_latency, 2)
        )


# Global metrics collector instance
global_metrics = MetricsCollector()
