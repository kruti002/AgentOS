"""
Base MCP Server abstraction.
"""

from abc import ABC, abstractmethod
from typing import List
from agentos.mcp.registry import ToolDefinition, ToolRegistry


class BaseMCPServer(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def register_tools(self, registry: ToolRegistry) -> None:
        """Register server tools with the provided ToolRegistry."""
        pass
