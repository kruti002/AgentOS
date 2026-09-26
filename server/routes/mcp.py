"""
MCP Tool discovery and manual invocation routes.
"""

from fastapi import APIRouter
from agentos.runtime.orchestrator import global_orchestrator
from agentos.runtime.state import ToolCallRequest

router = APIRouter(prefix="/api/mcp", tags=["MCP"])


@router.get("/tools")
async def list_tools():
    """List all registered MCP tools and their schemas."""
    tools = global_orchestrator.mcp_gateway.list_tools()
    return [
        {
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "risk_level": t.risk_level,
            "parameters": {
                name: param.model_dump() for name, param in t.parameters.items()
            },
            "schema": t.to_json_schema()
        }
        for t in tools
    ]


@router.post("/execute")
async def execute_tool_direct(req: ToolCallRequest):
    """Directly invoke an MCP tool through gateway."""
    res = global_orchestrator.mcp_gateway.execute_tool(req)
    return res.model_dump()
