"""
Unit tests for Observability, OpenTelemetry Tracer, Metrics, and Trajectory.
"""

import pytest
from agentos.observability.tracer import OpenTelemetryTracer
from agentos.observability.metrics import MetricsCollector, CostCalculator
from agentos.observability.trajectory import TrajectoryPublisher, TrajectoryEvent


def test_tracer_spans_and_tree():
    tracer = OpenTelemetryTracer()
    root = tracer.start_span("ParentTask", "orchestrator")
    child = tracer.start_span("ChildTool", "tool", parent_span_id=root.span_id)
    
    tracer.end_span(child, status="OK")
    tracer.end_span(root, status="OK")
    
    assert root.duration_ms >= 0
    assert child.duration_ms >= 0
    
    tree = tracer.get_trace_tree()
    assert len(tree) == 1
    assert tree[0]["name"] == "ParentTask"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["name"] == "ChildTool"


def test_cost_calculator():
    cost = CostCalculator.calculate_cost("gemini-2.5-flash", prompt_tokens=1000, completion_tokens=500)
    assert cost > 0
    assert isinstance(cost, float)


def test_metrics_collector_summary():
    collector = MetricsCollector()
    collector.record_task_completion(
        task_id="t1",
        success=True,
        duration_ms=450.0,
        tokens_used=500,
        cost_usd=0.00015,
        failures_count=2,
        recovered_count=2
    )
    collector.record_recovery_event(18.5)
    
    summary = collector.get_summary()
    assert summary.total_tasks == 1
    assert summary.task_success_rate == 100.0
    assert summary.recovery_rate == 100.0
    assert summary.total_failures_recovered == 2
