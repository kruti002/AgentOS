"""
Math & Analytics MCP Server.
"""

from typing import Dict, Any, List, Optional
import math
from agentos.mcp.servers.base import BaseMCPServer
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter


class CalcMCPServer(BaseMCPServer):
    def __init__(self):
        super().__init__(name="calc_mcp")

    def calc_eval(self, expression: str) -> Dict[str, Any]:
        """Safely evaluate mathematical expressions."""
        # Safe mathematical globals
        safe_dict = {
            "abs": abs, "round": round, "min": min, "max": max, "sum": sum, "pow": pow,
            "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "exp": math.exp,
            "sin": math.sin, "cos": math.cos, "tan": math.tan, "pi": math.pi, "e": math.e
        }
        
        cleaned = expression.strip()
        # Security: block double underscores, builtins
        if "__" in cleaned or "import" in cleaned or "eval" in cleaned or "exec" in cleaned:
            raise PermissionError("Unsafe expression syntax detected.")
            
        try:
            # Evaluate using restricted environment
            result = eval(cleaned, {"__builtins__": {}}, safe_dict)
            return {
                "expression": expression,
                "result": result
            }
        except Exception as e:
            raise ValueError(f"Failed to evaluate expression: {str(e)}")

    def data_stats(self, values: List[float]) -> Dict[str, Any]:
        """Calculate summary statistics on a list of numbers."""
        if not values:
            raise ValueError("Input list of values cannot be empty.")
            
        n = len(values)
        mean_val = sum(values) / n
        sorted_vals = sorted(values)
        median_val = sorted_vals[n // 2] if n % 2 != 0 else (sorted_vals[n//2 - 1] + sorted_vals[n//2]) / 2.0
        min_val = sorted_vals[0]
        max_val = sorted_vals[-1]
        variance = sum((x - mean_val) ** 2 for x in values) / n
        std_dev = math.sqrt(variance)
        
        return {
            "count": n,
            "mean": round(mean_val, 4),
            "median": round(median_val, 4),
            "min": round(min_val, 4),
            "max": round(max_val, 4),
            "std_dev": round(std_dev, 4)
        }

    def register_tools(self, registry: ToolRegistry) -> None:
        registry.register(ToolDefinition(
            name="calc_eval",
            description="Evaluate mathematical calculations (supports math functions like sqrt, log, sin, pow).",
            category="analytics",
            risk_level="LOW",
            parameters={
                "expression": ToolParameter(name="expression", type="string", description="Mathematical expression e.g. 'sqrt(144) + 25 * 3'")
            },
            handler=self.calc_eval
        ))
        
        registry.register(ToolDefinition(
            name="data_stats",
            description="Compute summary statistics (mean, median, min, max, std_dev) on a numerical array.",
            category="analytics",
            risk_level="LOW",
            parameters={
                "values": ToolParameter(name="values", type="array", description="List of numeric float values")
            },
            handler=self.data_stats
        ))
