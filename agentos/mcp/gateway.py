"""
Model Context Protocol (MCP) Gateway and Server Manager.
"""

from typing import Dict, Any, List, Optional
import time
from agentos.mcp.registry import ToolRegistry, ToolDefinition
from agentos.mcp.servers import (
    BaseMCPServer,
    FilesystemMCPServer,
    DatabaseMCPServer,
    WebMCPServer,
    ShellMCPServer,
    CalcMCPServer,
    HTTPClientMCPServer,
    GitMCPServer,
    CodeSandboxMCPServer,
)
from agentos.runtime.state import ToolCallRequest, ToolCallResult


class MCPGateway:
    def __init__(self, registry: Optional[ToolRegistry] = None):
        self.registry = registry or ToolRegistry()
        self.servers: Dict[str, BaseMCPServer] = {}
        self._init_default_servers()

    def _init_default_servers(self):
        """Mount built-in tool servers."""
        fs = FilesystemMCPServer()
        db = DatabaseMCPServer()
        web = WebMCPServer()
        shell = ShellMCPServer()
        calc = CalcMCPServer()
        http = HTTPClientMCPServer()
        git = GitMCPServer()
        code = CodeSandboxMCPServer()

        self.mount_server(fs)
        self.mount_server(db)
        self.mount_server(web)
        self.mount_server(shell)
        self.mount_server(calc)
        self.mount_server(http)
        self.mount_server(git)
        self.mount_server(code)

    def mount_server(self, server: BaseMCPServer) -> None:
        """Register a server and index its tools in the registry."""
        self.servers[server.name] = server
        server.register_tools(self.registry)

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self.registry.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[ToolDefinition]:
        return self.registry.list_tools(category)

    def execute_tool_call(self, tool_call: Any) -> ToolCallResult:
        """Execute a native LLMToolCall (name + arguments) via the gateway."""
        request = ToolCallRequest(
            tool_name=getattr(tool_call, "name", ""),
            arguments=getattr(tool_call, "arguments", {}) or {},
        )
        return self.execute_tool(request)

    def execute_tool(self, request: ToolCallRequest) -> ToolCallResult:
        """Execute a tool call with strict error interception and performance metrics."""
        tool_def = self.registry.get(request.tool_name)
        start_time = time.time()
        
        if not tool_def:
            return ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Tool '{request.tool_name}' is not registered in MCP Gateway.",
                execution_time_ms=(time.time() - start_time) * 1000
            )

        if not tool_def.handler:
            return ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Tool '{request.tool_name}' has no registered execution handler.",
                execution_time_ms=(time.time() - start_time) * 1000
            )

        # Validate required arguments
        for param_name, param_info in tool_def.parameters.items():
            if param_info.required and param_name not in request.arguments:
                return ToolCallResult(
                    call_id=request.call_id,
                    tool_name=request.tool_name,
                    success=False,
                    error_message=f"Missing required parameter '{param_name}' for tool '{request.tool_name}'.",
                    execution_time_ms=(time.time() - start_time) * 1000
                )

        try:
            # Filter arguments to expected parameters
            valid_args = {}
            for k, v in request.arguments.items():
                if k in tool_def.parameters:
                    valid_args[k] = v
                else:
                    # Pass through anyway if handler accepts kwargs
                    valid_args[k] = v

            output = tool_def.handler(**valid_args)
            exec_time = (time.time() - start_time) * 1000

            return ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=True,
                output=output,
                execution_time_ms=exec_time,
                is_sandboxed=True
            )

        except Exception as e:
            exec_time = (time.time() - start_time) * 1000
            return ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                error_message=str(e),
                execution_time_ms=exec_time,
                is_sandboxed=True
            )
