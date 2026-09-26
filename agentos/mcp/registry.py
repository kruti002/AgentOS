"""
Dynamic Tool Registry with schema parsing, categorization, and cross-model export.
"""

from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field
import inspect
import json


class ToolParameter(BaseModel):
    name: str
    type: str  # "string", "number", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    category: str = "general"  # "filesystem", "database", "web", "system", "analytics"
    risk_level: str = "LOW"    # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    parameters: Dict[str, ToolParameter] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    handler: Optional[Callable] = Field(default=None, exclude=True)

    def to_json_schema(self) -> Dict[str, Any]:
        """Export as standard JSON Schema compatible with OpenAI/Gemini/Anthropic function calling."""
        properties = {}
        required = []
        for param_name, param in self.parameters.items():
            prop: Dict[str, Any] = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param_name] = prop
            
            if param.required:
                required.append(param_name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool.name] = tool

    def register_func(
        self,
        name: str,
        description: str,
        category: str = "general",
        risk_level: str = "LOW",
        tags: Optional[List[str]] = None
    ):
        """Decorator to register a Python function as a tool."""
        def decorator(func: Callable):
            sig = inspect.signature(func)
            params = {}
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls", "ctx"):
                    continue
                param_type = "string"
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation in (list, List):
                    param_type = "array"
                elif param.annotation in (dict, Dict):
                    param_type = "object"
                
                is_required = param.default == inspect.Parameter.empty
                default_val = None if is_required else param.default

                params[param_name] = ToolParameter(
                    name=param_name,
                    type=param_type,
                    description=f"Parameter {param_name}",
                    required=is_required,
                    default=default_val
                )

            tool_def = ToolDefinition(
                name=name,
                description=description,
                category=category,
                risk_level=risk_level,
                parameters=params,
                tags=tags or [],
                handler=func
            )
            self.register(tool_def)
            return func
        return decorator

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[ToolDefinition]:
        if category:
            return [t for t in self._tools.values() if t.category == category]
        return list(self._tools.values())

    def export_all_schemas(self) -> List[Dict[str, Any]]:
        return [t.to_json_schema() for t in self._tools.values()]
