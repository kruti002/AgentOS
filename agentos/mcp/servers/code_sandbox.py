"""
Python Code Sandbox MCP Server.

Executes short Python snippets in a separate subprocess with a timeout, inside
the sandbox working directory. This is HIGH risk: it is subject to the security
policy (which requires human approval by default) and should never run
untrusted code without a gate.
"""

from typing import Dict, Any
import subprocess
import sys
import os

from agentos.mcp.servers.base import BaseMCPServer
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter
from agentos.config import settings


class CodeSandboxMCPServer(BaseMCPServer):
    def __init__(self, working_dir: str = None):
        super().__init__(name="code_sandbox_mcp")
        self.working_dir = working_dir or settings.sandbox_dir
        os.makedirs(self.working_dir, exist_ok=True)

    def py_exec(self, code: str, timeout_seconds: float = 8.0) -> Dict[str, Any]:
        """Run a Python snippet in a subprocess and capture stdout/stderr."""
        if not code or not code.strip():
            raise ValueError("No code provided.")

        try:
            result = subprocess.run(
                [sys.executable, "-I", "-c", code],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout.strip()[:8000],
                "stderr": result.stderr.strip()[:4000],
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": f"Timed out after {timeout_seconds}s.", "success": False}
        except Exception as e:
            return {"exit_code": -1, "stdout": "", "stderr": str(e), "success": False}

    def register_tools(self, registry: ToolRegistry) -> None:
        registry.register(ToolDefinition(
            name="py_exec",
            description="Execute a short Python snippet in an isolated subprocess and return its output.",
            category="system",
            risk_level="HIGH",
            parameters={
                "code": ToolParameter(name="code", type="string", description="Python source to execute"),
                "timeout_seconds": ToolParameter(name="timeout_seconds", type="number", description="Max seconds", required=False, default=8.0),
            },
            handler=self.py_exec,
        ))
