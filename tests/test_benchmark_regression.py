"""
Deterministic regression tests for the resilience benchmark and the heuristic
planner. These run with the LLM disabled so they are fast, deterministic, and
require no live endpoint — suitable for CI.
"""

import pytest

from agentos.evaluation.benchmark_runner import BenchmarkRunner
from agentos.runtime.planner import GoalPlanner
from agentos.mcp.gateway import MCPGateway


@pytest.mark.asyncio
async def test_benchmark_agentos_beats_baseline():
    """AgentOS (self-healing) must clearly outperform the non-resilient baseline."""
    runner = BenchmarkRunner(use_llm=False)
    report = await runner.run_full_suite(limit=40)

    # The non-resilient baseline should fail a large share of injected-fault tasks.
    assert report.baseline_success_rate <= 60.0
    # AgentOS should recover the vast majority of them.
    assert report.agentos_success_rate >= 90.0
    # And the lift must be positive and meaningful.
    assert report.agentos_success_rate - report.baseline_success_rate >= 30.0
    # Security threats must be prevented.
    assert report.agentos_security_prevented_rate >= 90.0


def _disabled_planner() -> GoalPlanner:
    planner = GoalPlanner()
    planner.llm.disabled = True  # force the deterministic heuristic path
    return planner


def _tools():
    return MCPGateway().registry.export_all_schemas()


def test_golden_plan_web_goal():
    planner = _disabled_planner()
    plan = planner.create_initial_plan("Search the web for distributed consensus", _tools())
    assert len(plan) >= 1
    assert plan[0].assigned_tool == "web_search"


def test_golden_plan_database_goal():
    planner = _disabled_planner()
    plan = planner.create_initial_plan("Run a SQL query against the database table", _tools())
    assert len(plan) >= 2
    assert plan[0].assigned_tool == "db_schema"
    assert any(s.assigned_tool == "db_query" for s in plan)


def test_golden_plan_file_write_goal():
    planner = _disabled_planner()
    plan = planner.create_initial_plan("Write a report and save it to a file", _tools())
    assert len(plan) >= 2
    assert any(s.assigned_tool == "fs_write" for s in plan)


def test_golden_plan_shell_goal():
    planner = _disabled_planner()
    plan = planner.create_initial_plan("Run a shell command to check the process", _tools())
    assert any(s.assigned_tool == "shell_exec" for s in plan)
