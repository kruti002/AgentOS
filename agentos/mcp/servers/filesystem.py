"""
Filesystem MCP Server. Provides safe sandboxed filesystem operations.
"""

from typing import Dict, Any, Optional, List
import os
from pathlib import Path
from agentos.mcp.servers.base import BaseMCPServer
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter
from agentos.config import settings


class FilesystemMCPServer(BaseMCPServer):
    def __init__(self, sandbox_root: Optional[str] = None):
        super().__init__(name="filesystem_mcp")
        self.sandbox_root = Path(sandbox_root or settings.sandbox_dir).resolve()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, path_str: str) -> Path:
        """Resolve path and verify it doesn't escape sandbox."""
        p = Path(path_str)
        if not p.is_absolute():
            resolved = (self.sandbox_root / p).resolve()
        else:
            resolved = p.resolve()
            
        if settings.enforce_sandbox:
            try:
                resolved.relative_to(self.sandbox_root)
            except ValueError:
                # If path escapes sandbox, restrict it to sandbox relative path
                resolved = (self.sandbox_root / p.name).resolve()
        return resolved

    def fs_read(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        """Read text from a file within the sandbox."""
        resolved = self._resolve_safe_path(path)
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"File '{path}' does not exist.")
            
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        if start_line is not None or end_line is not None:
            s = max(1, start_line or 1) - 1
            e = min(len(lines), end_line or len(lines))
            content = "".join(lines[s:e])
        else:
            content = "".join(lines)
            
        return {
            "path": str(resolved),
            "total_lines": len(lines),
            "content": content
        }

    def fs_write(self, path: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
        """Write text content to a file safely."""
        resolved = self._resolve_safe_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        
        if resolved.exists() and not overwrite:
            raise FileExistsError(f"File '{path}' already exists and overwrite is False.")
            
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
            
        return {
            "path": str(resolved),
            "bytes_written": len(content.encode("utf-8")),
            "status": "success"
        }

    def fs_list(self, path: str = ".") -> Dict[str, Any]:
        """List contents of a directory."""
        resolved = self._resolve_safe_path(path)
        if not resolved.exists() or not resolved.is_dir():
            raise NotADirectoryError(f"Directory '{path}' does not exist.")
            
        entries = []
        for entry in os.scandir(resolved):
            entries.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size_bytes": entry.stat().st_size if not entry.is_dir() else 0
            })
            
        return {
            "directory": str(resolved),
            "total_entries": len(entries),
            "entries": entries
        }

    def fs_stat(self, path: str) -> Dict[str, Any]:
        """Retrieve file or directory metadata."""
        resolved = self._resolve_safe_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Path '{path}' does not exist.")
        stat = resolved.stat()
        return {
            "path": str(resolved),
            "is_dir": resolved.is_dir(),
            "size_bytes": stat.st_size,
            "modified_time": stat.st_mtime
        }

    def register_tools(self, registry: ToolRegistry) -> None:
        registry.register(ToolDefinition(
            name="fs_read",
            description="Read text content from a file with optional line range slice.",
            category="filesystem",
            risk_level="LOW",
            parameters={
                "path": ToolParameter(name="path", type="string", description="Relative or absolute path to read"),
                "start_line": ToolParameter(name="start_line", type="integer", description="1-indexed starting line number", required=False),
                "end_line": ToolParameter(name="end_line", type="integer", description="1-indexed ending line number", required=False)
            },
            handler=self.fs_read
        ))
        
        registry.register(ToolDefinition(
            name="fs_write",
            description="Write text content to a destination file in the workspace.",
            category="filesystem",
            risk_level="MEDIUM",
            parameters={
                "path": ToolParameter(name="path", type="string", description="Destination file path"),
                "content": ToolParameter(name="content", type="string", description="Text content to write"),
                "overwrite": ToolParameter(name="overwrite", type="boolean", description="Whether to overwrite existing file", required=False, default=True)
            },
            handler=self.fs_write
        ))
        
        registry.register(ToolDefinition(
            name="fs_list",
            description="List entries (files and directories) in a given path.",
            category="filesystem",
            risk_level="LOW",
            parameters={
                "path": ToolParameter(name="path", type="string", description="Directory path to inspect", required=False, default=".")
            },
            handler=self.fs_list
        ))
        
        registry.register(ToolDefinition(
            name="fs_stat",
            description="Get metadata info (size, modified time, is_dir) for a path.",
            category="filesystem",
            risk_level="LOW",
            parameters={
                "path": ToolParameter(name="path", type="string", description="File or directory path")
            },
            handler=self.fs_stat
        ))
