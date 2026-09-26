"""
Goal decomposition, task planning, and replanning engine.

Primary path: an LLM (via the OpenAI-compatible FreeLLMAPI endpoint) decomposes
the goal into a sequence of subtasks, each mapped to an available tool. When the
LLM is unavailable or returns unusable output, a deterministic heuristic planner
takes over so the runtime always produces a valid plan.
"""

from typing import List, Dict, Any, Optional
import json

from agentos.runtime.state import AgentState, SubTask, TaskStatus
from agentos.llm.client import LLMClient, LLMUnavailable, global_llm


PLANNER_SYSTEM_PROMPT = """You are the planning module of AgentOS, an autonomous agent runtime.
Decompose the user's goal into an ordered list of concrete subtasks.

Rules:
- Each subtask must map to exactly one available tool, or to null for a pure
  reasoning/synthesis step that needs no tool.
- Only use tools from the provided catalog. Never invent tool names.
- Prefer the smallest number of steps that fully accomplishes the goal.
- The final step should usually be a null-tool synthesis/verification step.

Respond with ONLY a JSON object of this exact shape:
{
  "subtasks": [
    {"title": "short title", "description": "what this step does", "tool": "tool_name_or_null"}
  ]
}"""


class GoalPlanner:
    def __init__(self, model_name: Optional[str] = None, llm: Optional[LLMClient] = None):
        self.llm = llm or global_llm
        self.model_name = model_name or self.llm.model
        # Token usage from the most recent LLM planning call (0 when heuristic).
        self.last_prompt_tokens: int = 0
        self.last_completion_tokens: int = 0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def create_initial_plan(self, goal: str, available_tools: List[Dict[str, Any]]) -> List[SubTask]:
        """Decompose a goal into subtasks, LLM-first with heuristic fallback."""
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0

        if self.llm.available:
            llm_plan = self._llm_plan(goal, available_tools)
            if llm_plan:
                return llm_plan

        return self._heuristic_plan(goal, available_tools)

    def replan_on_failure(
        self,
        state: AgentState,
        failed_task: SubTask,
        failure_reason: str,
        available_tools: List[Dict[str, Any]],
    ) -> List[SubTask]:
        """Insert a recovery subtask after a failed step, LLM-first with fallback."""
        tool_names = [t.get("name", "") for t in available_tools]
        alternative_tool: Optional[str] = None

        if self.llm.available:
            alternative_tool = self._llm_choose_alternative(
                failed_task, failure_reason, tool_names
            )

        if not alternative_tool:
            alternative_tool = self._find_alternative_tool(failed_task.assigned_tool, available_tools)

        updated_plan: List[SubTask] = []
        for task in state.plan:
            if task.id == failed_task.id:
                task.status = TaskStatus.FAILED
                task.result = f"Failed: {failure_reason}"
                updated_plan.append(task)
                updated_plan.append(
                    SubTask(
                        title=f"Fallback for: {task.title}",
                        description=f"Alternative path due to: {failure_reason}",
                        assigned_tool=alternative_tool,
                    )
                )
            else:
                updated_plan.append(task)
        return updated_plan

    # ------------------------------------------------------------------ #
    # LLM-backed planning
    # ------------------------------------------------------------------ #
    def _llm_plan(self, goal: str, available_tools: List[Dict[str, Any]]) -> Optional[List[SubTask]]:
        """Ask the LLM to decompose the goal. Returns None on any failure."""
        tool_catalog = self._format_tool_catalog(available_tools)
        tool_names = {t.get("name", "") for t in available_tools}

        user_prompt = (
            f"Goal:\n{goal.strip()}\n\n"
            f"Available tools:\n{tool_catalog}\n\n"
            "Produce the plan as specified."
        )

        try:
            parsed, response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model_name,
                temperature=0.1,
                max_tokens=900,
            )
        except LLMUnavailable:
            return None

        # Always record the tokens actually spent, even if parsing fails and we
        # fall back to heuristics — the call was made and must be accounted for.
        self.last_prompt_tokens = response.usage.prompt_tokens
        self.last_completion_tokens = response.usage.completion_tokens

        subtasks = self._parse_plan(parsed, tool_names)
        return subtasks or None

    def _llm_choose_alternative(
        self,
        failed_task: SubTask,
        failure_reason: str,
        tool_names: List[str],
    ) -> Optional[str]:
        """Ask the LLM to pick a fallback tool for a failed step."""
        prompt = (
            "A subtask failed and needs an alternative tool.\n"
            f"Failed subtask: {failed_task.title} - {failed_task.description}\n"
            f"Failed tool: {failed_task.assigned_tool}\n"
            f"Failure reason: {failure_reason}\n"
            f"Available tools: {', '.join(t for t in tool_names if t)}\n\n"
            'Respond with ONLY JSON: {"tool": "tool_name_or_null"}'
        )
        try:
            parsed, _ = self.llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                temperature=0.0,
                max_tokens=100,
            )
        except LLMUnavailable:
            return None

        if isinstance(parsed, dict):
            tool = parsed.get("tool")
            if isinstance(tool, str) and tool in tool_names:
                return tool
        return None

    def _parse_plan(self, parsed: Any, tool_names: set) -> List[SubTask]:
        """Validate and convert parsed LLM JSON into SubTask objects."""
        if not parsed:
            return []

        raw_subtasks: Any = None
        if isinstance(parsed, dict):
            raw_subtasks = parsed.get("subtasks") or parsed.get("plan") or parsed.get("steps")
        elif isinstance(parsed, list):
            raw_subtasks = parsed

        if not isinstance(raw_subtasks, list) or not raw_subtasks:
            return []

        subtasks: List[SubTask] = []
        for item in raw_subtasks:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "Subtask").strip()
            description = str(item.get("description") or item.get("desc") or title).strip()

            tool = item.get("tool", item.get("assigned_tool"))
            if isinstance(tool, str):
                tool = tool.strip()
                if tool.lower() in ("null", "none", ""):
                    tool = None
                elif tool not in tool_names:
                    # LLM referenced an unknown tool; treat as reasoning step.
                    tool = None
            else:
                tool = None

            subtasks.append(
                SubTask(title=title[:120], description=description[:500], assigned_tool=tool)
            )

        return subtasks

    @staticmethod
    def _format_tool_catalog(available_tools: List[Dict[str, Any]]) -> str:
        """Render tool schemas as a compact catalog for the prompt."""
        lines = []
        for t in available_tools:
            name = t.get("name", "")
            if not name:
                continue
            desc = t.get("description", "")
            params = t.get("parameters", {}).get("properties", {})
            param_names = ", ".join(params.keys()) if params else "none"
            lines.append(f"- {name}: {desc} (params: {param_names})")
        return "\n".join(lines) if lines else "(no tools available)"

    # ------------------------------------------------------------------ #
    # Deterministic heuristic fallback (used when the LLM is unavailable)
    # ------------------------------------------------------------------ #
    def _heuristic_plan(self, goal: str, available_tools: List[Dict[str, Any]]) -> List[SubTask]:
        """Rule-based decomposition heuristics + tool mapping."""
        cleaned_goal = goal.strip()
        tool_names = [t.get("name", "") for t in available_tools]
        subtasks: List[SubTask] = []

        if any(w in cleaned_goal.lower() for w in ["search", "find", "research", "lookup", "who is", "what is"]):
            subtasks.append(SubTask(
                title="Information Discovery",
                description=f"Search and retrieve authoritative information for: {cleaned_goal}",
                assigned_tool="web_search" if "web_search" in tool_names else "search_web",
            ))
            subtasks.append(SubTask(
                title="Data Synthesis",
                description="Analyze discovered facts and synthesize clear, actionable response.",
                assigned_tool=None,
            ))

        elif any(w in cleaned_goal.lower() for w in ["file", "directory", "read", "write", "list files", "save", "log"]):
            if "write" in cleaned_goal.lower() or "save" in cleaned_goal.lower() or "create" in cleaned_goal.lower():
                subtasks.append(SubTask(
                    title="Inspect & Prepare Target",
                    description="Inspect environment or directory structure for target path.",
                    assigned_tool="fs_list" if "fs_list" in tool_names else "fs_read",
                ))
                subtasks.append(SubTask(
                    title="Write File Content",
                    description="Persist the required content to the filesystem safely.",
                    assigned_tool="fs_write",
                ))
            else:
                subtasks.append(SubTask(
                    title="Read & Inspect Files",
                    description="Read target file or directory contents.",
                    assigned_tool="fs_read",
                ))

        elif any(w in cleaned_goal.lower() for w in ["sql", "database", "query", "table", "duckdb", "sqlite"]):
            subtasks.append(SubTask(
                title="Inspect DB Schema",
                description="Query table metadata and schemas to ensure valid SQL generation.",
                assigned_tool="db_schema",
            ))
            subtasks.append(SubTask(
                title="Execute Analytical Query",
                description="Run structured query and extract results.",
                assigned_tool="db_query",
            ))
            subtasks.append(SubTask(
                title="Summarize Query Insights",
                description="Present query metrics in clear tabular and narrative format.",
                assigned_tool=None,
            ))

        elif any(w in cleaned_goal.lower() for w in ["run", "command", "bash", "shell", "exec", "process"]):
            subtasks.append(SubTask(
                title="Security Policy Check",
                description="Validate shell command against execution security policies.",
                assigned_tool=None,
            ))
            subtasks.append(SubTask(
                title="Execute Sandboxed Command",
                description=f"Run command safely: {cleaned_goal}",
                assigned_tool="shell_exec",
            ))

        else:
            subtasks.append(SubTask(
                title="Analyze Goal & Environment",
                description=f"Evaluate prerequisites and available tools for: {cleaned_goal}",
                assigned_tool=None,
            ))
            subtasks.append(SubTask(
                title="Execute Core Action",
                description="Perform primary tool invocation or computational step.",
                assigned_tool=tool_names[0] if tool_names else None,
            ))
            subtasks.append(SubTask(
                title="Verify & Finalize Result",
                description="Validate output completeness against original goal.",
                assigned_tool=None,
            ))

        return subtasks

    def _find_alternative_tool(self, failed_tool: Optional[str], available_tools: List[Dict[str, Any]]) -> Optional[str]:
        tool_names = [t.get("name", "") for t in available_tools]
        fallbacks = {
            "web_search": ["duckduckgo_search", "web_fetch", "fs_read"],
            "db_query": ["db_raw_query", "db_schema"],
            "fs_write": ["fs_append", "shell_exec"],
            "shell_exec": ["fs_read", "calc_eval"],
        }
        if failed_tool in fallbacks:
            for alt in fallbacks[failed_tool]:
                if alt in tool_names:
                    return alt
        return tool_names[0] if tool_names else None
