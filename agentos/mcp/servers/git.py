"""
Git MCP Server. Read-only git inspection over the workspace repository.
"""

from typing import Dict, Any, Optional
import subprocess

from agentos.mcp.servers.base import BaseMCPServer
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter
from agentos.config import settings


class GitMCPServer(BaseMCPServer):
    def __init__(self, repo_dir: Optional[str] = None):
        super().__init__(name="git_mcp")
        self.repo_dir = repo_dir or settings.workspace_root

    def _run_git(self, args: list, timeout: float = 10.0) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "command": "git " + " ".join(args),
                "exit_code": result.returncode,
                "stdout": result.stdout.strip()[:8000],
                "stderr": result.stderr.strip()[:2000],
                "success": result.returncode == 0,
            }
        except FileNotFoundError:
            return {"success": False, "error": "git is not installed or not on PATH."}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "git command timed out."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def git_status(self) -> Dict[str, Any]:
        """Show the working tree status (porcelain)."""
        return self._run_git(["status", "--porcelain=v1", "--branch"])

    def git_log(self, max_count: int = 10) -> Dict[str, Any]:
        """Show recent commit history."""
        n = max(1, min(int(max_count or 10), 100))
        return self._run_git(["log", f"-{n}", "--oneline", "--decorate"])

    def git_diff(self, path: Optional[str] = None) -> Dict[str, Any]:
        """Show unstaged changes, optionally for a single path."""
        args = ["diff", "--stat"]
        if path:
            args.append(path)
        return self._run_git(args)

    def register_tools(self, registry: ToolRegistry) -> None:
        registry.register(ToolDefinition(
            name="git_status",
            description="Show git working tree status for the workspace repository.",
            category="system",
            risk_level="LOW",
            parameters={},
            handler=self.git_status,
        ))
        registry.register(ToolDefinition(
            name="git_log",
            description="Show recent git commit history (one line per commit).",
            category="system",
            risk_level="LOW",
            parameters={
                "max_count": ToolParameter(name="max_count", type="integer", description="Number of commits", required=False, default=10),
            },
            handler=self.git_log,
        ))
        registry.register(ToolDefinition(
            name="git_diff",
            description="Show a summary of unstaged changes, optionally for one path.",
            category="system",
            risk_level="LOW",
            parameters={
                "path": ToolParameter(name="path", type="string", description="Optional path to diff", required=False),
            },
            handler=self.git_diff,
        ))
