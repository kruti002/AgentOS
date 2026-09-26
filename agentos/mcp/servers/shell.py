"""
Sandboxed Shell Execution MCP Server.
"""

from typing import Dict, Any, List, Optional
import subprocess
import os
from agentos.mcp.servers.base import BaseMCPServer
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter
from agentos.config import settings


class ShellMCPServer(BaseMCPServer):
    def __init__(self, working_dir: Optional[str] = None):
        super().__init__(name="shell_mcp")
        self.working_dir = working_dir or settings.sandbox_dir
        os.makedirs(self.working_dir, exist_ok=True)
        
        # Prohibited command patterns for safety
        self.blocked_patterns = [
            "rm -rf /", "rmdir /s /q c:\\", "format ", "mkfs",
            ":(){ :|:& };:", "del /f /s /q c:\\", "shutdown"
        ]

    def shell_exec(self, command: str, timeout_seconds: float = 10.0) -> Dict[str, Any]:
        """Execute a shell command within the sandboxed working directory."""
        cmd_lower = command.lower().strip()
        for blocked in self.blocked_patterns:
            if blocked in cmd_lower:
                raise PermissionError(f"Command contains prohibited dangerous instruction: '{blocked}'")
                
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            return {
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout_seconds} seconds.",
                "success": False
            }
        except Exception as e:
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }

    def register_tools(self, registry: ToolRegistry) -> None:
        registry.register(ToolDefinition(
            name="shell_exec",
            description="Execute a safe shell command inside the sandboxed environment.",
            category="system",
            risk_level="HIGH",
            parameters={
                "command": ToolParameter(name="command", type="string", description="Command string to run"),
                "timeout_seconds": ToolParameter(name="timeout_seconds", type="number", description="Timeout in seconds", required=False, default=10.0)
            },
            handler=self.shell_exec
        ))
