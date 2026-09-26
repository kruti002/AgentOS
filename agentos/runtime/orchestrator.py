"""
AgentOS Core Orchestrator and Lifecycle Controller.
"""

from typing import Dict, Any, List, Optional, AsyncGenerator
import asyncio
import time
import uuid
import json

from agentos.runtime.state import (
    AgentState,
    ExecutionPhase,
    TaskStatus,
    StepTrace,
    ToolCallRequest,
    ToolCallResult,
    PendingApproval,
    PolicyDecision,
    FailureType,
    RecoveryStrategy
)
from agentos.runtime.planner import GoalPlanner
from agentos.runtime.memory import MemoryStore
from agentos.mcp.gateway import MCPGateway
from agentos.security.policy_engine import SecurityPolicyEngine
from agentos.security.injection_detector import PromptInjectionDetector
from agentos.reliability.failure_detector import FailureDetector
from agentos.reliability.repair_engine import SchemaRepairEngine
from agentos.reliability.loop_detector import SemanticLoopDetector
from agentos.reliability.retry_engine import RetryEngine
from agentos.reliability.replanner import SelfHealingReplanner
from agentos.evaluation.fault_injector import FaultInjector
from agentos.observability.tracer import global_tracer, TraceSpan
from agentos.observability.metrics import global_metrics, CostCalculator
from agentos.observability.trajectory import trajectory_bus, TrajectoryEvent
from agentos.llm.client import LLMClient, LLMUnavailable, global_llm
from agentos.storage import global_store
from agentos.memory import global_memory
from agentos.config import settings


class AgentOrchestrator:
    def __init__(
        self,
        mcp_gateway: Optional[MCPGateway] = None,
        policy_engine: Optional[SecurityPolicyEngine] = None,
        model_name: Optional[str] = None,
        llm: Optional[LLMClient] = None,
    ):
        self.llm = llm or global_llm
        self.model_name = model_name or self.llm.model
        self.mcp_gateway = mcp_gateway or MCPGateway()
        self.policy_engine = policy_engine or SecurityPolicyEngine()
        self.injection_detector = PromptInjectionDetector()
        self.failure_detector = FailureDetector()
        self.schema_repair = SchemaRepairEngine()
        self.loop_detector = SemanticLoopDetector()
        self.retry_engine = RetryEngine()
        self.replanner = SelfHealingReplanner(self.mcp_gateway.registry)
        self.planner = GoalPlanner(model_name=self.model_name, llm=self.llm)
        self.memory = MemoryStore()
        self._active_tasks: Dict[str, AgentState] = {}
        # When False, failures/injections are detected and recorded but no
        # recovery is applied. Used to measure a non-resilient baseline.
        self.self_healing_enabled: bool = True
        self.fault_injector = FaultInjector(fault_probability=1.0)
        self._pending_fault: Optional[str] = None
        # Human-in-the-loop approval coordination: approval_id -> {event, approved}
        self._approvals: Dict[str, Dict[str, Any]] = {}
        # How long to wait for a human decision before auto-denying (seconds).
        self.approval_timeout_seconds: float = 300.0

    def _record_usage(self, state: AgentState, prompt_tokens: int, completion_tokens: int) -> int:
        """Accumulate real token usage onto the task state. Returns step total."""
        prompt_tokens = max(0, int(prompt_tokens or 0))
        completion_tokens = max(0, int(completion_tokens or 0))
        state.total_prompt_tokens += prompt_tokens
        state.total_completion_tokens += completion_tokens
        step_total = prompt_tokens + completion_tokens
        state.total_tokens += step_total
        return step_total

    def _task_spans(self, task_id: str) -> list:
        """Collect the root span for a task and all its descendants."""
        all_spans = global_tracer.recorded_spans
        root = next((s for s in all_spans if s.name.endswith(task_id)), None)
        if root is None:
            return []
        keep_ids = {root.span_id}
        # Walk the tree (spans are appended in creation order; iterate to fixpoint).
        changed = True
        while changed:
            changed = False
            for s in all_spans:
                if s.parent_span_id in keep_ids and s.span_id not in keep_ids:
                    keep_ids.add(s.span_id)
                    changed = True
        return [s for s in all_spans if s.span_id in keep_ids]

    def _persist(self, state: AgentState) -> None:
        """Write a durable record of the finished task (best-effort, non-fatal)."""
        try:
            global_store.save_task(state, model=self.model_name)
            # Persist spans belonging to this task's root span subtree. The root
            # span is named "AgentTask: {task_id}"; collect it and its descendants.
            spans = self._task_spans(state.task_id)
            global_store.save_spans(state.task_id, spans)
            global_store.save_metric(
                task_id=state.task_id,
                success=state.status == TaskStatus.COMPLETED,
                duration_ms=state.total_duration_ms,
                tokens_used=state.total_tokens,
                cost_usd=state.total_cost_usd,
                failures_count=state.failure_count,
                recovered_count=state.recovered_count,
            )
            # Store the outcome in long-term memory for future recall.
            if state.status == TaskStatus.COMPLETED and state.final_output:
                global_memory.add(
                    text=state.final_output[:1000],
                    metadata={"goal": state.goal, "task_id": state.task_id},
                )
        except Exception:
            pass

    def get_task_state(self, task_id: str) -> Optional[AgentState]:
        return self._active_tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Request cancellation of a running task. The execution loop stops at
        the next subtask boundary. Returns True if the task was active."""
        state = self._active_tasks.get(task_id)
        if state is None:
            return False
        if state.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return False
        state.status = TaskStatus.CANCELLED
        return True

    def resolve_approval(self, approval_id: str, approved: bool) -> bool:
        """Resolve a pending human-in-the-loop approval. Returns True if found."""
        entry = self._approvals.get(approval_id)
        if entry is None:
            return False
        entry["approved"] = bool(approved)
        entry["event"].set()
        return True

    async def _await_approval(self, state: AgentState, tool_req: ToolCallRequest, reason: str) -> bool:
        """Pause the task until a human approves/denies the tool call.

        Returns True if approved, False if denied or timed out.
        """
        approval = PendingApproval(
            task_id=state.task_id,
            tool_name=tool_req.tool_name,
            arguments=tool_req.arguments,
            reason=reason,
        )
        event = asyncio.Event()
        self._approvals[approval.approval_id] = {"event": event, "approved": False}

        state.pending_approval = approval
        prev_status = state.status
        state.status = TaskStatus.WAITING_APPROVAL

        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id,
            event_type="APPROVAL_REQUIRED",
            payload=approval.model_dump(),
        ))

        try:
            await asyncio.wait_for(event.wait(), timeout=self.approval_timeout_seconds)
            approved = self._approvals.get(approval.approval_id, {}).get("approved", False)
        except asyncio.TimeoutError:
            approved = False
        finally:
            self._approvals.pop(approval.approval_id, None)
            state.pending_approval = None
            # Restore running status unless the task was cancelled meanwhile.
            if state.status == TaskStatus.WAITING_APPROVAL:
                state.status = prev_status

        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id,
            event_type="APPROVAL_RESOLVED",
            payload={"approval_id": approval.approval_id, "approved": approved},
        ))
        return approved

    ITERATIVE_SYSTEM_PROMPT = (
        "You are AgentOS, an autonomous agent. Achieve the user's goal by "
        "calling the provided tools. Observe each tool result and decide the "
        "next action. Use ONLY data returned by tools; never invent facts, "
        "table columns, or numbers. When you have enough information, stop "
        "calling tools and reply with a concise final answer."
    )

    async def _run_iterative(self, state: AgentState, root_span: TraceSpan) -> AgentState:
        """ReAct-style loop: the LLM observes tool results and picks the next action."""
        state.current_phase = ExecutionPhase.EXECUTION
        tool_schemas = self.mcp_gateway.registry.export_all_schemas()

        system_prompt = self.ITERATIVE_SYSTEM_PROMPT
        # Retrieval-augmented memory: inject relevant past outcomes.
        try:
            recalled = global_memory.recall_context(state.goal, k=3)
        except Exception:
            recalled = ""
        if recalled:
            system_prompt = f"{system_prompt}\n\n{recalled}"

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state.goal},
        ]

        final_answer = ""
        for _ in range(settings.max_iterations):
            if state.status == TaskStatus.CANCELLED:
                break

            state.current_step += 1
            think_span = global_tracer.start_span(
                f"Reason (iter {state.current_step})", "llm", root_span.span_id
            )
            resp = self.llm.chat_with_tools(
                messages=messages,
                tools=tool_schemas,
                model=self.model_name,
                temperature=0.1,
                max_tokens=800,
            )
            self._record_usage(state, resp.usage.prompt_tokens, resp.usage.completion_tokens)
            global_tracer.end_span(think_span)

            # No tool calls -> the model produced its final answer. Re-issue the
            # final turn as a stream so the UI receives tokens as they arrive.
            if not resp.tool_calls:
                final_answer = self._stream_final_answer(state, messages, root_span.span_id)
                if not final_answer:
                    final_answer = (resp.content or "").strip()
                break

            # Record the assistant turn (with tool_calls) into the transcript.
            messages.append({
                "role": "assistant",
                "content": resp.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in resp.tool_calls
                ],
            })

            # Execute each requested tool call through the resilient pipeline.
            for tc in resp.tool_calls:
                result_text = await self._execute_iterative_tool_call(state, tc, root_span.span_id)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })

        if state.status == TaskStatus.CANCELLED:
            return self._finalize_cancelled(state, root_span)

        # Finalize as completed.
        state.current_phase = ExecutionPhase.SYNTHESIS
        state.status = TaskStatus.COMPLETED
        state.final_output = final_answer or self._synthesize_final_output(state)
        state.end_time = time.time()
        state.total_duration_ms = (state.end_time - state.start_time) * 1000
        global_tracer.end_span(root_span, status="OK")

        state.total_cost_usd = CostCalculator.calculate_cost(
            self.model_name, state.total_prompt_tokens, state.total_completion_tokens
        )
        global_metrics.record_task_completion(
            task_id=state.task_id, success=True, duration_ms=state.total_duration_ms,
            tokens_used=state.total_tokens, cost_usd=state.total_cost_usd,
            failures_count=state.failure_count, recovered_count=state.recovered_count,
        )
        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id,
            event_type="COMPLETED",
            payload={
                "final_output": state.final_output,
                "total_tokens": state.total_tokens,
                "total_cost_usd": state.total_cost_usd,
                "duration_ms": state.total_duration_ms,
                "failures_recovered": state.recovered_count,
            },
        ))
        self._persist(state)
        return state

    async def _execute_iterative_tool_call(self, state: AgentState, tc: Any, parent_span_id: str) -> str:
        """Run one LLM-requested tool call through policy, execution, and healing.

        Returns a text observation to feed back to the model.
        """
        tool_req = ToolCallRequest(tool_name=tc.name, arguments=tc.arguments or {})
        step_trace = StepTrace(
            step_index=state.current_step,
            phase=ExecutionPhase.EXECUTION,
            thought=f"Tool call: {tc.name}",
            tool_call=tool_req,
        )

        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id,
            event_type="STEP_START",
            payload={"step_index": state.current_step, "subtask": tc.name, "thought": step_trace.thought},
        ))

        # Security policy.
        decision, reason = self.policy_engine.evaluate(tool_req)
        step_trace.policy_decision = decision
        step_trace.policy_reason = reason
        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id,
            event_type="SECURITY_CHECK",
            payload={"decision": decision.value, "reason": reason, "tool": tc.name},
        ))
        if decision == PolicyDecision.BLOCKED:
            heal_evt = self.replanner.handle_failure(
                state=state, step_index=state.current_step,
                failure_type=FailureType.PERMISSION_DENIED,
                strategy=RecoveryStrategy.TOOL_FALLBACK,
                original_error=f"Blocked by policy: {reason}", failed_request=tool_req,
            )
            step_trace.healing_events.append(heal_evt)
            state.history.append(step_trace)
            return f"ERROR: tool '{tc.name}' blocked by security policy: {reason}"

        if decision == PolicyDecision.REQUIRE_APPROVAL:
            approved = await self._await_approval(state, tool_req, reason)
            if not approved:
                step_trace.policy_reason = f"{reason} (approval denied)"
                state.history.append(step_trace)
                return (
                    f"ERROR: tool '{tc.name}' requires human approval and was "
                    f"denied ({reason}). Try an alternative approach."
                )

        # Execution (with optional fault injection).
        tool_span = global_tracer.start_span(f"MCPTool: {tc.name}", "tool", parent_span_id)
        tool_result = None
        if self._pending_fault:
            fault = self._pending_fault
            self._pending_fault = None
            tool_result = self.fault_injector.inject_fault(tool_req, fault)
        if tool_result is None:
            tool_result = self.mcp_gateway.execute_tool(tool_req)

        # Failure detection + self-healing.
        fail_type, rec_strategy = self.failure_detector.classify_tool_result(tool_result)
        if fail_type != FailureType.NONE and self.self_healing_enabled:
            heal_span = global_tracer.start_span(f"SelfHealing: {fail_type.value}", "healing", parent_span_id)
            if rec_strategy == RecoveryStrategy.SCHEMA_AUTO_REPAIR:
                tool_def = self.mcp_gateway.get_tool(tc.name)
                if tool_def:
                    tool_req.arguments = self.schema_repair.repair_arguments(tool_def, tool_req.arguments)
                    tool_result = self.mcp_gateway.execute_tool(tool_req)
            elif rec_strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF:
                await asyncio.sleep(0.3)
                tool_result = self.mcp_gateway.execute_tool(tool_req)
            heal_evt = self.replanner.handle_failure(
                state=state, step_index=state.current_step, failure_type=fail_type,
                strategy=rec_strategy, original_error=tool_result.error_message or "Execution anomaly",
                failed_request=tool_req,
            )
            step_trace.healing_events.append(heal_evt)
            global_tracer.end_span(heal_span)
            trajectory_bus.publish(TrajectoryEvent(
                event_id=f"evt_{uuid.uuid4().hex[:6]}",
                task_id=state.task_id, event_type="HEALING", payload=heal_evt.model_dump(),
            ))

        # Prompt-injection scan on tool output.
        if tool_result.success and tool_result.output:
            is_injected, _ = self.injection_detector.scan(str(tool_result.output))
            if is_injected:
                tool_result.tainted = True
                tool_result.output = self.injection_detector.sanitize_untrusted_data(tool_result.output)

        step_trace.tool_result = tool_result
        global_tracer.end_span(tool_span, status="OK" if tool_result.success else "ERROR")

        if tool_result.success:
            observation = str(tool_result.output)[:2000]
            self.memory.store_scratchpad(f"step_{state.current_step}_result", tool_result.output)
        else:
            observation = f"ERROR: {tool_result.error_message}"

        state.history.append(step_trace)
        self.memory.save_checkpoint(state)
        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id, event_type="STEP_END",
            payload={"step_index": state.current_step, "success": tool_result.success, "output": observation[:300]},
        ))
        return observation

    def _stream_final_answer(self, state: AgentState, messages: List[Dict[str, Any]], parent_span_id: str) -> str:
        """Generate the final answer as a token stream, emitting TOKEN events."""
        stream_span = global_tracer.start_span("Final Answer (stream)", "llm", parent_span_id)

        def on_delta(piece: str) -> None:
            trajectory_bus.publish(TrajectoryEvent(
                event_id=f"evt_{uuid.uuid4().hex[:6]}",
                task_id=state.task_id,
                event_type="TOKEN",
                payload={"delta": piece},
            ))

        try:
            resp = self.llm.chat_stream(
                messages=messages,
                model=self.model_name,
                temperature=0.2,
                max_tokens=800,
                on_delta=on_delta,
            )
            self._record_usage(state, resp.usage.prompt_tokens, resp.usage.completion_tokens)
            text = (resp.content or "").strip()
        except LLMUnavailable:
            text = ""
        finally:
            global_tracer.end_span(stream_span)
        return text

    def _finalize_cancelled(self, state: AgentState, root_span: TraceSpan) -> AgentState:
        state.end_time = time.time()
        state.total_duration_ms = (state.end_time - state.start_time) * 1000
        state.final_output = "# AgentOS Task Cancelled\n\nExecution was cancelled before completion."
        global_tracer.end_span(root_span, status="ERROR", error="cancelled")
        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id, event_type="CANCELLED",
            payload={"message": "Task cancelled by request."},
        ))
        self._persist(state)
        return state

    async def run_task(
        self,
        goal: str,
        task_id: Optional[str] = None,
        inject_fault: Optional[str] = None,
        mode: str = "auto",
    ) -> AgentState:
        """Execute an end-to-end resilient agent task.

        ``mode`` selects the execution strategy:
          - "auto" (default): iterative ReAct loop when the LLM supports native
            tool-calling, otherwise the plan-then-execute path.
          - "iterative": force the ReAct loop (falls back if LLM unavailable).
          - "plan": force plan-then-execute.

        When ``inject_fault`` is a fault-type string, a single fault of that
        type is injected on the first tool call, letting benchmarks exercise
        the self-healing machinery deterministically.
        """
        state = AgentState(
            task_id=task_id or f"task_{uuid.uuid4().hex[:8]}",
            goal=goal,
            status=TaskStatus.RUNNING
        )
        self._active_tasks[state.task_id] = state
        # Per-run fault injection flag (consumed on the first tool call).
        self._pending_fault: Optional[str] = inject_fault

        # Create root trace span
        root_span = global_tracer.start_span(
            name=f"AgentTask: {state.task_id}",
            category="orchestrator",
            attributes={"goal": goal, "model": self.model_name, "task_id": state.task_id}
        )

        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id,
            event_type="TASK_START",
            payload={"goal": goal, "task_id": state.task_id}
        ))

        use_iterative = mode == "iterative" or (mode == "auto" and self.llm.supports_tools())
        if use_iterative:
            try:
                return await self._run_iterative(state, root_span)
            except LLMUnavailable:
                # Fall through to the deterministic plan-then-execute path.
                pass

        try:
            # Phase 1: Planning
            state.current_phase = ExecutionPhase.PLANNING
            plan_span = global_tracer.start_span("Goal Decomposition", "planning", root_span.span_id)
            
            avail_tools = self.mcp_gateway.registry.export_all_schemas()
            state.plan = self.planner.create_initial_plan(goal, avail_tools)
            self._record_usage(state, self.planner.last_prompt_tokens, self.planner.last_completion_tokens)
            self.memory.save_checkpoint(state)
            
            global_tracer.end_span(plan_span)
            
            trajectory_bus.publish(TrajectoryEvent(
                event_id=f"evt_{uuid.uuid4().hex[:6]}",
                task_id=state.task_id,
                event_type="PLAN_CREATED",
                payload={"plan": [t.model_dump() for t in state.plan]}
            ))

            # Phase 2: Execution Loop over subtasks
            for subtask_idx, subtask in enumerate(state.plan):
                if state.status == TaskStatus.CANCELLED:
                    break

                subtask.status = TaskStatus.RUNNING
                state.current_step += 1
                
                # Execute step for this subtask
                await self._execute_subtask(state, subtask, root_span.span_id)

                if subtask.status == TaskStatus.FAILED:
                    # Attempt replanning
                    state.plan = self.planner.replan_on_failure(state, subtask, subtask.result or "Tool error", avail_tools)

            # If the task was cancelled mid-execution, finalize as cancelled
            # instead of synthesizing a completed result.
            if state.status == TaskStatus.CANCELLED:
                state.end_time = time.time()
                state.total_duration_ms = (state.end_time - state.start_time) * 1000
                state.final_output = "# AgentOS Task Cancelled\n\nExecution was cancelled before completion."
                global_tracer.end_span(root_span, status="ERROR", error="cancelled")
                trajectory_bus.publish(TrajectoryEvent(
                    event_id=f"evt_{uuid.uuid4().hex[:6]}",
                    task_id=state.task_id,
                    event_type="CANCELLED",
                    payload={"message": "Task cancelled by request."},
                ))
                self._persist(state)
                return state

            # Phase 3: Result Synthesis
            state.current_phase = ExecutionPhase.SYNTHESIS
            state.status = TaskStatus.COMPLETED
            synth_span = global_tracer.start_span("Result Synthesis", "llm", root_span.span_id)
            
            final_output = self._synthesize_final_output(state)
            state.final_output = final_output
            state.end_time = time.time()
            state.total_duration_ms = (state.end_time - state.start_time) * 1000

            global_tracer.end_span(synth_span)
            global_tracer.end_span(root_span, status="OK")

            # Calculate total costs from measured token usage.
            state.total_cost_usd = CostCalculator.calculate_cost(
                self.model_name,
                state.total_prompt_tokens,
                state.total_completion_tokens,
            )

            # Record global metrics
            global_metrics.record_task_completion(
                task_id=state.task_id,
                success=True,
                duration_ms=state.total_duration_ms,
                tokens_used=state.total_tokens,
                cost_usd=state.total_cost_usd,
                failures_count=state.failure_count,
                recovered_count=state.recovered_count
            )

            trajectory_bus.publish(TrajectoryEvent(
                event_id=f"evt_{uuid.uuid4().hex[:6]}",
                task_id=state.task_id,
                event_type="COMPLETED",
                payload={
                    "final_output": final_output,
                    "total_tokens": state.total_tokens,
                    "total_cost_usd": state.total_cost_usd,
                    "duration_ms": state.total_duration_ms,
                    "failures_recovered": state.recovered_count
                }
            ))

            self._persist(state)
            return state

        except Exception as e:
            state.status = TaskStatus.FAILED
            state.error = str(e)
            state.end_time = time.time()
            state.total_duration_ms = (state.end_time - state.start_time) * 1000
            
            global_tracer.end_span(root_span, status="ERROR", error=str(e))
            
            trajectory_bus.publish(TrajectoryEvent(
                event_id=f"evt_{uuid.uuid4().hex[:6]}",
                task_id=state.task_id,
                event_type="FAILED",
                payload={"error": str(e)}
            ))
            self._persist(state)
            return state

    async def _execute_subtask(self, state: AgentState, subtask: Any, parent_span_id: str) -> None:
        """Execute an individual subtask with policy check and self-healing loop."""
        step_start_time = time.time()
        tool_name = subtask.assigned_tool

        step_trace = StepTrace(
            step_index=state.current_step,
            phase=ExecutionPhase.EXECUTION,
            thought=f"Executing subtask: {subtask.title} - {subtask.description}"
        )

        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id,
            event_type="STEP_START",
            payload={"step_index": state.current_step, "subtask": subtask.title, "thought": step_trace.thought}
        ))

        # Check semantic loop detector before execution
        is_loop, loop_msg = self.loop_detector.check_for_loop(state.history)
        if is_loop:
            heal_evt = self.replanner.handle_failure(
                state=state,
                step_index=state.current_step,
                failure_type=FailureType.SEMANTIC_LOOP,
                strategy=RecoveryStrategy.SEMANTIC_LOOP_BREAKER,
                original_error=loop_msg or "Execution cycle detected"
            )
            step_trace.healing_events.append(heal_evt)
            trajectory_bus.publish(TrajectoryEvent(
                event_id=f"evt_{uuid.uuid4().hex[:6]}",
                task_id=state.task_id,
                event_type="HEALING",
                payload=heal_evt.model_dump()
            ))

        if not tool_name:
            # Pure analytical/reasoning step: run it through the LLM when
            # available, otherwise record a lightweight completion.
            analysis, p_tok, c_tok = self._reason_step(state, subtask)
            step_trace.tokens_used = self._record_usage(state, p_tok, c_tok)
            subtask.status = TaskStatus.COMPLETED
            subtask.result = analysis
            step_trace.duration_ms = (time.time() - step_start_time) * 1000
            state.history.append(step_trace)
            return

        # Prepare tool arguments (LLM-driven with heuristic fallback).
        tool_args, arg_p_tok, arg_c_tok = self._derive_tool_args(subtask, state)
        self._record_usage(state, arg_p_tok, arg_c_tok)
        tool_req = ToolCallRequest(tool_name=tool_name, arguments=tool_args)
        step_trace.tool_call = tool_req

        # Security Policy Evaluation
        state.current_phase = ExecutionPhase.POLICY_CHECK
        sec_span = global_tracer.start_span(f"SecurityCheck: {tool_name}", "security", parent_span_id)
        
        decision, reason = self.policy_engine.evaluate(tool_req)
        step_trace.policy_decision = decision
        step_trace.policy_reason = reason
        global_tracer.end_span(sec_span, status="OK" if decision != PolicyDecision.BLOCKED else "ERROR")

        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id,
            event_type="SECURITY_CHECK",
            payload={"decision": decision.value, "reason": reason, "tool": tool_name}
        ))

        if decision == PolicyDecision.BLOCKED:
            heal_evt = self.replanner.handle_failure(
                state=state,
                step_index=state.current_step,
                failure_type=FailureType.PERMISSION_DENIED,
                strategy=RecoveryStrategy.TOOL_FALLBACK,
                original_error=f"Blocked by policy: {reason}",
                failed_request=tool_req
            )
            step_trace.healing_events.append(heal_evt)
            subtask.status = TaskStatus.FAILED
            subtask.result = f"Blocked by Security Policy: {reason}"
            state.history.append(step_trace)
            return

        # Tool Execution via MCP Gateway
        state.current_phase = ExecutionPhase.EXECUTION
        tool_span = global_tracer.start_span(f"MCPTool: {tool_name}", "tool", parent_span_id)

        # Optional deterministic fault injection (consumed once per run).
        tool_result = None
        if self._pending_fault:
            fault = self._pending_fault
            self._pending_fault = None
            tool_result = self.fault_injector.inject_fault(tool_req, fault)
        if tool_result is None:
            tool_result = self.mcp_gateway.execute_tool(tool_req)

        # Failure Detection & Self-Healing Loop
        fail_type, rec_strategy = self.failure_detector.classify_tool_result(tool_result)

        if fail_type != FailureType.NONE:
            if not self.self_healing_enabled:
                # Non-resilient baseline: record the failure, apply no recovery.
                global_tracer.end_span(tool_span, status="ERROR")
                if fail_type == FailureType.PROMPT_INJECTION_DETECTED:
                    # Baseline does not sanitize; the tainted output flows through.
                    subtask.status = TaskStatus.COMPLETED
                    subtask.result = str(tool_result.output)[:300]
                else:
                    subtask.status = TaskStatus.FAILED
                    subtask.result = tool_result.error_message or "Unrecovered failure"
                step_trace.tool_result = tool_result
                step_trace.tokens_used = arg_p_tok + arg_c_tok
                step_trace.duration_ms = (time.time() - step_start_time) * 1000
                state.history.append(step_trace)
                return

            # Self-healing intervention
            heal_span = global_tracer.start_span(f"SelfHealing: {fail_type.value}", "healing", parent_span_id)

            # Execute repair if schema issue
            if rec_strategy == RecoveryStrategy.SCHEMA_AUTO_REPAIR:
                tool_def = self.mcp_gateway.get_tool(tool_name)
                if tool_def:
                    repaired_args = self.schema_repair.repair_arguments(tool_def, tool_req.arguments)
                    tool_req.arguments = repaired_args
                    # Retry tool with repaired arguments
                    tool_result = self.mcp_gateway.execute_tool(tool_req)

            elif rec_strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF:
                # Retry with backoff (the injected transient fault is now cleared)
                await asyncio.sleep(0.3)
                tool_result = self.mcp_gateway.execute_tool(tool_req)

            heal_evt = self.replanner.handle_failure(
                state=state,
                step_index=state.current_step,
                failure_type=fail_type,
                strategy=rec_strategy,
                original_error=tool_result.error_message or "Execution anomaly",
                failed_request=tool_req
            )
            step_trace.healing_events.append(heal_evt)
            global_tracer.end_span(heal_span)

            trajectory_bus.publish(TrajectoryEvent(
                event_id=f"evt_{uuid.uuid4().hex[:6]}",
                task_id=state.task_id,
                event_type="HEALING",
                payload=heal_evt.model_dump()
            ))

        # Check prompt injection on tool output
        if tool_result.success and tool_result.output:
            is_injected, _ = self.injection_detector.scan(str(tool_result.output))
            if is_injected:
                tool_result.tainted = True
                tool_result.output = self.injection_detector.sanitize_untrusted_data(tool_result.output)

        step_trace.tool_result = tool_result
        global_tracer.end_span(tool_span, status="OK" if tool_result.success else "ERROR")

        if tool_result.success:
            subtask.status = TaskStatus.COMPLETED
            subtask.result = str(tool_result.output)[:2000]
            # Store full output in working memory for grounding later steps.
            self.memory.store_scratchpad(f"step_{state.current_step}_result", tool_result.output)
        else:
            subtask.status = TaskStatus.FAILED
            subtask.result = tool_result.error_message

        step_trace.tokens_used = arg_p_tok + arg_c_tok
        step_trace.duration_ms = (time.time() - step_start_time) * 1000
        state.history.append(step_trace)

        # Save state checkpoint
        self.memory.save_checkpoint(state)

        trajectory_bus.publish(TrajectoryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:6]}",
            task_id=state.task_id,
            event_type="STEP_END",
            payload={"step_index": state.current_step, "success": tool_result.success, "output": subtask.result}
        ))

    def _collect_prior_results(self, state: AgentState) -> str:
        """Gather the actual outputs of completed steps for grounding.

        Pulls full tool outputs from working memory (not the truncated
        summaries) so reasoning steps operate on real data rather than a
        status digest, which is what caused earlier hallucinations.
        """
        blocks: List[str] = []
        for step in state.history:
            if step.tool_call is None:
                continue
            tool = step.tool_call.tool_name
            stored = self.memory.get_scratchpad(f"step_{step.step_index}_result")
            if stored is not None:
                value = stored
            elif step.tool_result is not None:
                value = step.tool_result.output if step.tool_result.success else step.tool_result.error_message
            else:
                continue
            text = str(value)
            if len(text) > 1500:
                text = text[:1500] + " …(truncated)"
            blocks.append(f"[{tool}] -> {text}")

        return "\n".join(blocks) if blocks else "(no prior tool results)"

    def _reason_step(self, state: AgentState, subtask: Any) -> tuple[str, int, int]:
        """Execute a pure reasoning subtask via the LLM. Returns (text, p_tok, c_tok)."""
        if not self.llm.available:
            return f"Completed analysis for {subtask.title}", 0, 0

        prior_results = self._collect_prior_results(state)
        system = (
            "You are the reasoning module of an autonomous agent. Use ONLY the "
            "data provided in the prior tool results. Do NOT invent services, "
            "numbers, rows, or facts that are not present in that data. If the "
            "data is insufficient to complete the step, say so explicitly."
        )
        prompt = (
            f"Overall goal: {state.goal}\n\n"
            f"Current reasoning subtask: {subtask.title}\n"
            f"Objective: {subtask.description}\n\n"
            f"Prior tool results (the ONLY source of truth):\n{prior_results}\n\n"
            "Perform this reasoning step grounded strictly in the data above. "
            "Respond concisely with no preamble."
        )
        try:
            resp = self.llm.chat(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                model=self.model_name,
                temperature=0.0,
                max_tokens=500,
            )
        except LLMUnavailable:
            return f"Completed analysis for {subtask.title}", 0, 0

        text = (resp.content or "").strip() or f"Completed analysis for {subtask.title}"
        return text[:1200], resp.usage.prompt_tokens, resp.usage.completion_tokens

    def _derive_tool_args(self, subtask: Any, state: AgentState) -> tuple[Dict[str, Any], int, int]:
        """Synthesize tool arguments. LLM-driven when available, else heuristics.

        Returns (arguments, prompt_tokens, completion_tokens).
        """
        tool_name = subtask.assigned_tool
        tool_def = self.mcp_gateway.get_tool(tool_name)

        if self.llm.available and tool_def is not None:
            args, p_tok, c_tok = self._llm_tool_args(subtask, state, tool_def)
            if args is not None:
                return args, p_tok, c_tok

        return self._heuristic_tool_args(tool_name, state), 0, 0

    def _llm_tool_args(self, subtask: Any, state: AgentState, tool_def: Any) -> tuple[Optional[Dict[str, Any]], int, int]:
        """Ask the LLM to fill tool arguments from the tool schema and context."""
        schema = tool_def.to_json_schema()
        params = schema.get("parameters", {})
        # Ground argument generation in the actual outputs of prior steps (e.g.
        # a preceding db_schema result) so values like SQL column names are
        # correct rather than guessed.
        prior_results = self._collect_prior_results(state)

        prompt = (
            "Generate the arguments to call a tool for the current subtask.\n"
            f"Overall goal: {state.goal}\n"
            f"Subtask: {subtask.title} - {subtask.description}\n\n"
            f"Tool name: {tool_def.name}\n"
            f"Tool description: {tool_def.description}\n"
            f"Tool JSON schema (parameters): {json.dumps(params)}\n\n"
            f"Prior tool results (use these exact names/values; do not invent "
            f"column names, tables, or fields):\n{prior_results}\n\n"
            "Respond with ONLY a JSON object mapping each required parameter name "
            "to a concrete value appropriate for the goal. Include optional "
            "parameters only when useful."
        )
        try:
            parsed, resp = self.llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                temperature=0.0,
                max_tokens=400,
            )
        except LLMUnavailable:
            return None, 0, 0

        if not isinstance(parsed, dict):
            return None, resp.usage.prompt_tokens, resp.usage.completion_tokens

        # Keep only keys the tool actually declares.
        valid_keys = set(tool_def.parameters.keys())
        args = {k: v for k, v in parsed.items() if k in valid_keys}
        # If the model produced nothing usable, signal fallback.
        if not args:
            return None, resp.usage.prompt_tokens, resp.usage.completion_tokens
        return args, resp.usage.prompt_tokens, resp.usage.completion_tokens

    def _heuristic_tool_args(self, t_name: Optional[str], state: AgentState) -> Dict[str, Any]:
        """Deterministic default arguments used when the LLM is unavailable."""
        if t_name == "web_search":
            return {"query": state.goal, "max_results": 3}
        elif t_name == "web_fetch":
            return {"url": "https://agentos.dev/docs"}
        elif t_name == "fs_read":
            return {"path": "agentos_demo.txt"}
        elif t_name == "fs_write":
            return {"path": "agentos_demo.txt", "content": f"AgentOS Autonomous Report for goal: '{state.goal}'\nGenerated at: {time.ctime()}", "overwrite": True}
        elif t_name == "fs_list":
            return {"path": "."}
        elif t_name == "db_query":
            return {"query": "SELECT service_name, status, latency_ms FROM system_metrics WHERE cpu_usage > 20 ORDER BY latency_ms DESC;"}
        elif t_name == "db_schema":
            return {"table_name": "system_metrics"}
        elif t_name == "calc_eval":
            return {"expression": "sqrt(256) + 42 * 2"}
        elif t_name == "data_stats":
            return {"values": [12.4, 45.1, 18.9, 92.3, 33.7, 56.2]}
        elif t_name == "shell_exec":
            return {"command": "echo 'AgentOS Substrate Verified'"}
        return {}

    def _synthesize_final_output(self, state: AgentState) -> str:
        """Produce a markdown completion report, LLM-narrated when available."""
        # LLM-generated answer synthesis first, so token totals in the header
        # reflect the synthesis call as well.
        summary = self._llm_synthesis(state)

        lines = [
            f"# AgentOS Task Completion Report",
            f"**Goal:** {state.goal}",
            f"**Execution Status:** `{state.status.value.upper()}`",
            f"**Total Steps Executed:** {len(state.history)} | **Total Tokens:** {state.total_tokens:,}",
            "",
            "## Execution Timeline & Subtasks",
        ]

        for idx, sub in enumerate(state.plan, 1):
            status_emoji = "✅" if sub.status == TaskStatus.COMPLETED else "❌"
            tool_tag = f"`{sub.assigned_tool}`" if sub.assigned_tool else "_Direct Analysis_"
            lines.append(f"{idx}. {status_emoji} **{sub.title}** ({tool_tag})")
            if sub.result:
                lines.append(f"   > **Output:** {sub.result}")

        if state.healing_events:
            lines.append("")
            lines.append("## Self-Healing & Resilience Interventions")
            lines.append(f"The self-healing runtime detected and recovered from **{len(state.healing_events)}** execution anomalies:")
            for h in state.healing_events:
                status_icon = "🛡️ Recovered" if h.recovered else "⚠️ Unresolved"
                lines.append(f"- **Step {h.step_index}** ({h.failure_type.value}): {h.action_taken} ({status_icon} in {h.recovery_time_ms:.1f}ms)")

        lines.append("")
        lines.append("## Summary Conclusion")
        lines.append(summary)

        return "\n".join(lines)

    def _llm_synthesis(self, state: AgentState) -> str:
        """Generate a grounded natural-language answer from the execution results."""
        fallback = (
            "Task resolved by the AgentOS runtime control plane with full "
            "OpenTelemetry trace instrumentation."
        )
        if not self.llm.available:
            return fallback

        results = []
        for sub in state.plan:
            if sub.result:
                tool = sub.assigned_tool or "analysis"
                results.append(f"[{tool}] {sub.title}: {sub.result}")
        results_block = "\n".join(results) if results else "(no step outputs captured)"

        prompt = (
            "Synthesize a final answer for the user's goal using ONLY the "
            "execution results below. Be concise and factual; do not invent data.\n\n"
            f"Goal: {state.goal}\n\n"
            f"Execution results:\n{results_block}\n\n"
            "Write the final answer as a short markdown section."
        )
        try:
            resp = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                temperature=0.3,
                max_tokens=600,
            )
        except LLMUnavailable:
            return fallback

        self._record_usage(state, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return (resp.content or "").strip() or fallback


# Global default orchestrator
global_orchestrator = AgentOrchestrator()
