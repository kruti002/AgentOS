"""
Schema and JSON Auto-Repair Engine.
"""

from typing import Dict, Any, Optional
import json
import re
from agentos.mcp.registry import ToolDefinition


class SchemaRepairEngine:
    @staticmethod
    def clean_and_parse_json(raw_text: str) -> Optional[Dict[str, Any]]:
        """Attempt robust parsing and repair of malformed JSON strings."""
        if not raw_text or not isinstance(raw_text, str):
            return None

        text = raw_text.strip()

        # Strip markdown code blocks if present
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if match:
                text = match.group(1).strip()

        # First direct try
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Repair Strategy 1: Replace single quotes with double quotes
        repaired = text.replace("'", '"')
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Repair Strategy 2: Remove trailing commas before } or ]
        repaired = re.sub(r",\s*([\]}])", r"\1", repaired)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Repair Strategy 3: Wrap unquoted keys
        repaired = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)\s*:', r'\1"\2":', text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        return None

    def repair_arguments(
        self,
        tool_def: ToolDefinition,
        raw_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Auto-correct, coerce types, and inject defaults for tool arguments."""
        repaired = {}
        valid_params = tool_def.parameters

        # Map lowercase aliases
        param_lookup = {k.lower(): k for k in valid_params.keys()}

        for k, v in raw_args.items():
            clean_key = k
            # Check for misspelled or case mismatch
            if clean_key not in valid_params and clean_key.lower() in param_lookup:
                clean_key = param_lookup[clean_key.lower()]

            if clean_key in valid_params:
                param_spec = valid_params[clean_key]
                target_type = param_spec.type

                # Type coercion
                try:
                    if target_type == "integer" and isinstance(v, str):
                        repaired[clean_key] = int(re.sub(r"[^\d-]", "", v))
                    elif target_type == "number" and isinstance(v, str):
                        repaired[clean_key] = float(v)
                    elif target_type == "boolean" and isinstance(v, str):
                        repaired[clean_key] = v.lower() in ("true", "1", "yes", "t")
                    elif target_type == "array" and isinstance(v, str):
                        # Convert comma separated string to list
                        repaired[clean_key] = [item.strip() for item in v.split(",") if item.strip()]
                    elif target_type == "string" and not isinstance(v, str):
                        repaired[clean_key] = str(v)
                    else:
                        repaired[clean_key] = v
                except Exception:
                    repaired[clean_key] = v
            else:
                repaired[clean_key] = v

        # Inject missing required defaults if available
        for param_name, param_spec in valid_params.items():
            if param_spec.required and param_name not in repaired:
                if param_spec.default is not None:
                    repaired[param_name] = param_spec.default
                elif param_spec.type == "string":
                    repaired[param_name] = ""
                elif param_spec.type in ("integer", "number"):
                    repaired[param_name] = 0
                elif param_spec.type == "boolean":
                    repaired[param_name] = False
                elif param_spec.type == "array":
                    repaired[param_name] = []

        return repaired
