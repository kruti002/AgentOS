"""
Unit tests for AgentOS core runtime, state, memory, and planner.
"""

import pytest
import asyncio
from agentos.runtime.state import AgentState, TaskStatus, ExecutionPhase
from agentos.runtime.memory import MemoryStore
from agentos.runtime.planner import GoalPlanner
from agentos.runtime.orchestrator import AgentOrchestrator


def test_agent_state_initialization():
    state = AgentState(goal="Analyze cluster performance")
    assert state.status == TaskStatus.PENDING
    assert state.current_phase == ExecutionPhase.PLANNING
    assert len(state.history) == 0
    assert len(state.checkpoints) == 0


def test_memory_store_checkpoints():
    store = MemoryStore()
    state = AgentState(goal="Test goal", current_step=1)
    
    chk = store.save_checkpoint(state)
    assert chk.step_index == 1
    assert len(store.checkpoints) == 1
    
    state.current_step = 2
    restored = store.rollback_to_checkpoint(chk.checkpoint_id, state)
    assert restored is not None
    assert restored.current_step == 1


def test_goal_planner_decomposition():
    planner = GoalPlanner()
    available_tools = [
        {"name": "web_search"},
        {"name": "fs_read"},
        {"name": "db_query"},
    ]
    valid_tools = {t["name"] for t in available_tools}

    plan = planner.create_initial_plan("Search the web for distributed systems", available_tools)

    # A valid plan has steps, and every tool-bound step references a real tool.
    assert len(plan) >= 1
    for step in plan:
        assert step.title
        if step.assigned_tool is not None:
            assert step.assigned_tool in valid_tools

    # When the LLM is unavailable the deterministic heuristic runs and maps a
    # web/search goal to web_search first.
    if not planner.llm.available:
        assert plan[0].assigned_tool == "web_search"


@pytest.mark.asyncio
async def test_orchestrator_end_to_end():
    orchestrator = AgentOrchestrator()
    state = await orchestrator.run_task("Perform mathematical statistics analysis")

    assert state.status == TaskStatus.COMPLETED
    assert len(state.history) > 0
    assert state.final_output is not None

    # Token accounting must always be internally consistent and non-negative.
    # We do NOT assert tokens > 0 even when the LLM is available: some free
    # providers (via the router) omit usage fields, and a plan may fall back to
    # heuristics, both of which legitimately yield zero recorded tokens.
    assert state.total_tokens >= 0
    assert state.total_prompt_tokens >= 0
    assert state.total_completion_tokens >= 0
    assert state.total_tokens == state.total_prompt_tokens + state.total_completion_tokens
