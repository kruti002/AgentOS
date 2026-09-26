"""
Unit tests for MCP Gateway, Tool Registry, and built-in servers.
"""

import pytest
from agentos.mcp.gateway import MCPGateway
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter
from agentos.runtime.state import ToolCallRequest


def test_mcp_registry_registration():
    registry = ToolRegistry()
    tool = ToolDefinition(
        name="custom_echo",
        description="Echo string input",
        category="general",
        parameters={
            "text": ToolParameter(name="text", type="string", description="Text to echo")
        },
        handler=lambda text: f"echo: {text}"
    )
    registry.register(tool)
    
    found = registry.get("custom_echo")
    assert found is not None
    assert found.name == "custom_echo"
    
    schemas = registry.export_all_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "custom_echo"


def test_mcp_gateway_execution():
    gateway = MCPGateway()
    
    # Test calc_eval
    req = ToolCallRequest(
        tool_name="calc_eval",
        arguments={"expression": "10 * 5 + 2"}
    )
    result = gateway.execute_tool(req)
    assert result.success is True
    assert result.output["result"] == 52

    # Test data_stats
    req2 = ToolCallRequest(
        tool_name="data_stats",
        arguments={"values": [10.0, 20.0, 30.0]}
    )
    result2 = gateway.execute_tool(req2)
    assert result2.success is True
    assert result2.output["mean"] == 20.0
    assert result2.output["count"] == 3


def test_mcp_gateway_missing_args():
    gateway = MCPGateway()
    req = ToolCallRequest(
        tool_name="calc_eval",
        arguments={}  # missing required 'expression'
    )
    result = gateway.execute_tool(req)
    assert result.success is False
    assert "Missing required parameter" in result.error_message


def test_mcp_gateway_db_query():
    gateway = MCPGateway()
    req = ToolCallRequest(
        tool_name="db_query",
        arguments={"query": "SELECT * FROM system_metrics LIMIT 2;"}
    )
    result = gateway.execute_tool(req)
    assert result.success is True
    assert result.output["row_count"] == 2
