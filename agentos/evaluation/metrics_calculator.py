"""
Comparative Benchmark Metrics and Analysis Engine.
"""

from typing import Dict, Any, List
from pydantic import BaseModel, Field


class BenchmarkComparisonReport(BaseModel):
    total_scenarios_evaluated: int
    categories_tested: List[str]
    
    # Baseline Agent (No Self-Healing / No Policy Guard)
    baseline_success_rate: float
    baseline_failed_count: int
    baseline_mttr_ms: float
    baseline_security_leak_count: int
    baseline_avg_cost_usd: float
    
    # AgentOS Resilient Runtime
    agentos_success_rate: float
    agentos_recovered_count: int
    agentos_recovery_rate: float
    agentos_mttr_ms: float
    agentos_security_prevented_rate: float
    agentos_avg_cost_usd: float
    
    # Net Delta
    success_rate_lift_pct: float
    resilience_multiplier: float
    category_breakdowns: Dict[str, Dict[str, Any]]


class ComparativeEvaluator:
    @staticmethod
    def calculate_comparative_metrics(
        baseline_results: List[Dict[str, Any]],
        agentos_results: List[Dict[str, Any]]
    ) -> BenchmarkComparisonReport:
        total = len(agentos_results)
        if total == 0:
            raise ValueError("No benchmark results provided.")

        categories = sorted(list(set(r.get("category", "general") for r in agentos_results)))

        # Baseline stats
        b_success = sum(1 for r in baseline_results if r.get("success", False))
        b_rate = (b_success / total) * 100.0
        b_failed = total - b_success
        b_leaks = sum(1 for r in baseline_results if r.get("security_leaked", False))
        b_cost = sum(r.get("cost_usd", 0.0) for r in baseline_results) / total

        # AgentOS stats
        a_success = sum(1 for r in agentos_results if r.get("success", False))
        a_rate = (a_success / total) * 100.0
        a_recovered = sum(1 for r in agentos_results if r.get("was_healed", False) and r.get("success", False))
        a_recover_rate = (a_recovered / (total - b_success)) * 100.0 if (total - b_success) > 0 else 100.0
        a_mttr = sum(r.get("recovery_time_ms", 0.0) for r in agentos_results if r.get("was_healed")) / (a_recovered or 1)
        a_sec_prevent = sum(1 for r in agentos_results if r.get("security_blocked", False) or r.get("injection_sanitized", False))
        a_sec_rate = (a_sec_prevent / (b_leaks or 1)) * 100.0 if b_leaks > 0 else 100.0
        a_cost = sum(r.get("cost_usd", 0.0) for r in agentos_results) / total

        lift = a_rate - b_rate
        multiplier = round(a_rate / (b_rate or 1.0), 2)

        # Per Category Breakdown
        breakdowns = {}
        for cat in categories:
            cat_b = [r for r in baseline_results if r.get("category") == cat]
            cat_a = [r for r in agentos_results if r.get("category") == cat]
            b_cat_rate = (sum(1 for r in cat_b if r.get("success")) / (len(cat_b) or 1)) * 100.0
            a_cat_rate = (sum(1 for r in cat_a if r.get("success")) / (len(cat_a) or 1)) * 100.0
            breakdowns[cat] = {
                "total_tasks": len(cat_a),
                "baseline_success_pct": round(b_cat_rate, 1),
                "agentos_success_pct": round(a_cat_rate, 1),
                "recovery_rate_pct": round(((a_cat_rate - b_cat_rate) / (100 - b_cat_rate or 1)) * 100.0, 1) if b_cat_rate < 100 else 100.0
            }

        return BenchmarkComparisonReport(
            total_scenarios_evaluated=total,
            categories_tested=categories,
            baseline_success_rate=round(b_rate, 1),
            baseline_failed_count=b_failed,
            baseline_mttr_ms=0.0,  # Baseline never recovers
            baseline_security_leak_count=b_leaks,
            baseline_avg_cost_usd=round(b_cost, 6),
            agentos_success_rate=round(a_rate, 1),
            agentos_recovered_count=a_recovered,
            agentos_recovery_rate=round(a_recover_rate, 1),
            agentos_mttr_ms=round(a_mttr, 2),
            agentos_security_prevented_rate=round(min(100.0, a_sec_rate), 1),
            agentos_avg_cost_usd=round(a_cost, 6),
            success_rate_lift_pct=round(lift, 1),
            resilience_multiplier=multiplier,
            category_breakdowns=breakdowns
        )
