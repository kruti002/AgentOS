"""
Memory and State Checkpointing management for AgentOS.
"""

from typing import Any, Dict, List, Optional
import copy
from agentos.runtime.state import AgentState, Checkpoint


class MemoryStore:
    def __init__(self, max_history_tokens: int = 8000):
        self.max_history_tokens = max_history_tokens
        self.checkpoints: List[Checkpoint] = []
        self.working_memory: Dict[str, Any] = {}

    def save_checkpoint(self, state: AgentState) -> Checkpoint:
        """Create an immutable snapshot of the current state."""
        snapshot = copy.deepcopy(state.model_dump())
        chk = Checkpoint(
            step_index=state.current_step,
            state_snapshot=snapshot
        )
        self.checkpoints.append(chk)
        state.checkpoints.append(chk)
        return chk

    def rollback_to_checkpoint(self, checkpoint_id: str, state: AgentState) -> Optional[AgentState]:
        """Restore state from a previous checkpoint."""
        for chk in reversed(self.checkpoints):
            if chk.checkpoint_id == checkpoint_id:
                restored_data = copy.deepcopy(chk.state_snapshot)
                restored_state = AgentState.model_validate(restored_data)
                return restored_state
        return None

    def get_latest_checkpoint(self) -> Optional[Checkpoint]:
        return self.checkpoints[-1] if self.checkpoints else None

    def store_scratchpad(self, key: str, value: Any) -> None:
        self.working_memory[key] = value

    def get_scratchpad(self, key: str, default: Any = None) -> Any:
        return self.working_memory.get(key, default)

    def summarize_context(self, state: AgentState) -> str:
        """Generates a concise markdown summary of the execution history."""
        summary = [f"### Goal: {state.goal}", f"**Current Step:** {state.current_step}"]
        if state.plan:
            summary.append("#### Plan Progress:")
            for sub in state.plan:
                status_icon = "✅" if sub.status == "completed" else "⏳" if sub.status == "running" else "⚪"
                summary.append(f"- {status_icon} **{sub.title}**: {sub.description}")
        
        if state.history:
            summary.append("\n#### Recent Steps:")
            for step in state.history[-5:]:
                tool_info = f" [Tool: {step.tool_call.tool_name}]" if step.tool_call else ""
                res_info = f" -> {'Success' if step.tool_result and step.tool_result.success else 'Failed'}" if step.tool_result else ""
                summary.append(f"- Step {step.step_index} ({step.phase.value}){tool_info}{res_info}: {step.thought or 'Executing...'}")

        return "\n".join(summary)
