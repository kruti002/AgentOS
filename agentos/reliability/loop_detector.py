"""
Semantic Loop and Action Frequency Detector.
"""

from typing import List, Dict, Any, Optional
import hashlib
import json
from agentos.runtime.state import StepTrace, ToolCallRequest


class SemanticLoopDetector:
    def __init__(self, window_size: int = 4, max_identical_actions: int = 2):
        self.window_size = window_size
        self.max_identical_actions = max_identical_actions

    def _hash_action(self, tool_call: Optional[ToolCallRequest]) -> str:
        if not tool_call:
            return "NO_TOOL"
        # Create deterministic fingerprint of tool + sorted args
        clean_args = json.dumps(tool_call.arguments, sort_keys=True)
        raw = f"{tool_call.tool_name}::{clean_args}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def check_for_loop(self, history: List[StepTrace]) -> tuple[bool, Optional[str]]:
        """Inspect recent trajectory history for infinite or repetitive loops."""
        if len(history) < 2:
            return False, None

        recent_steps = history[-self.window_size:]
        action_hashes = [self._hash_action(s.tool_call) for s in recent_steps if s.tool_call]

        if not action_hashes:
            return False, None

        # Check 1: Consecutive identical actions
        if len(action_hashes) >= self.max_identical_actions:
            last_hash = action_hashes[-1]
            identical_count = sum(1 for h in action_hashes if h == last_hash)
            if identical_count >= self.max_identical_actions:
                last_tool = recent_steps[-1].tool_call.tool_name if recent_steps[-1].tool_call else "action"
                return True, f"Repetitive execution loop: tool '{last_tool}' invoked {identical_count} times with identical parameters."

        # Check 2: Alternating cyclic loop (A -> B -> A -> B)
        if len(action_hashes) >= 4:
            if action_hashes[-1] == action_hashes[-3] and action_hashes[-2] == action_hashes[-4]:
                return True, "Alternating oscillation loop detected between multiple tools."

        return False, None
