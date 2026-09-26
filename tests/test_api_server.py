"""
End-to-end integration tests for FastAPI Control Plane and SSE streaming.
"""

import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from server.main import app


@pytest.mark.asyncio
async def test_health_and_tools_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Health
        res = await ac.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"
        
        # Tools
        res_tools = await ac.get("/api/mcp/tools")
        assert res_tools.status_code == 200
        assert len(res_tools.json()) >= 5


@pytest.mark.asyncio
async def test_agent_run_and_state_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Dispatch task
        res = await ac.post("/api/agent/run", json={"goal": "Evaluate mathematical expression sqrt(100) + 50"})
        assert res.status_code == 200
        task_id = res.json()["task_id"]
        
        # Wait a moment for background task execution
        await asyncio.sleep(0.5)
        
        # Fetch task state
        res_state = await ac.get(f"/api/agent/state/{task_id}")
        assert res_state.status_code == 200
        state_data = res_state.json()
        assert state_data["task_id"] == task_id
        assert state_data["status"] in ("running", "completed")


@pytest.mark.asyncio
async def test_benchmark_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/benchmark/results")
        assert res.status_code == 200
        data = res.json()
        assert "agentos_success_rate" in data
        assert "baseline_success_rate" in data
        assert data["agentos_success_rate"] >= data["baseline_success_rate"]


@pytest.mark.asyncio
async def test_observability_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/observability/metrics")
        assert res.status_code == 200
        
        res_traces = await ac.get("/api/observability/traces")
        assert res_traces.status_code == 200
        assert "spans" in res_traces.json()
