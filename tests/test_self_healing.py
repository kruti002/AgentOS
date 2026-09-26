"""
Unit tests for Self-Healing Engine (failure detection, schema repair, loop detection, replanning).
"""

import pytest
from agentos.reliability.failure_detector import FailureDetector
from agentos.reliability.repair_engine import SchemaRepairEngine
from agentos.reliability.loop_detector import SemanticLoopDetector
from agentos.reliability.replanner import SelfHealingReplanner
from agentos.runtime.state import (
    ToolCallResult,
    ToolCallRequest,
    FailureType,
    RecoveryStrategy,
    AgentState,
    StepTrace,
    ExecutionPhase
)
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter


def test_failure_detector_classification():
    detector = FailureDetector()
    
    # 503 Gateway Timeout
    res1 = ToolCallResult(
        call_id="c1",
        tool_name="web_search",
        success=False,
        error_message="HTTP 503 Service Unavailable: Remote server timed out."
    )
    f_type1, strat1 = detector.classify_tool_result(res1)
    assert f_type1 == FailureType.TRANSIENT_API_ERROR
    assert strat1 == RecoveryStrategy.EXPONENTIAL_BACKOFF

    # Missing parameter / JSON error
    res2 = ToolCallResult(
        call_id="c2",
        tool_name="data_stats",
        success=False,
        error_message="TypeError: missing required parameter 'values'"
    )
    f_type2, strat2 = detector.classify_tool_result(res2)
    assert f_type2 == FailureType.SCHEMA_ARGUMENT_ERROR
    assert strat2 == RecoveryStrategy.SCHEMA_AUTO_REPAIR


def test_schema_repair_engine():
    engine = SchemaRepairEngine()
    
    # Test JSON repair
    malformed = "{'query': 'distributed systems', 'limit': 5,}"
    repaired = engine.clean_and_parse_json(malformed)
    assert repaired is not None
    assert repaired["query"] == "distributed systems"
    assert repaired["limit"] == 5

    # Test argument type coercion
    tool_def = ToolDefinition(
        name="test_calc",
        description="test",
        parameters={
            "count": ToolParameter(name="count", type="integer", description="count"),
            "enabled": ToolParameter(name="enabled", type="boolean", description="enabled"),
            "values": ToolParameter(name="values", type="array", description="items")
        }
    )
    raw_args = {"count": "42", "enabled": "true", "values": "1, 2, 3"}
    fixed = engine.repair_arguments(tool_def, raw_args)
    assert fixed["count"] == 42
    assert fixed["enabled"] is True
    assert fixed["values"] == ["1", "2", "3"]


def test_semantic_loop_detector():
    detector = SemanticLoopDetector(window_size=4, max_identical_actions=2)
    
    req = ToolCallRequest(tool_name="web_search", arguments={"query": "test query"})
    step1 = StepTrace(step_index=1, phase=ExecutionPhase.EXECUTION, tool_call=req)
    step2 = StepTrace(step_index=2, phase=ExecutionPhase.EXECUTION, tool_call=req)
    
    is_loop, msg = detector.check_for_loop([step1, step2])
    assert is_loop is True
    assert "Repetitive execution loop" in msg
