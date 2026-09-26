"""
Core state schemas, enums, and data models for AgentOS.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
import uuid
import time


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionPhase(str, Enum):
    PLANNING = "planning"
    TOOL_SELECT = "tool_select"
    POLICY_CHECK = "policy_check"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    HEALING = "healing"
    SYNTHESIS = "synthesis"


class FailureType(str, Enum):
    NONE = "none"
    TRANSIENT_API_ERROR = "transient_api_error"
    SCHEMA_ARGUMENT_ERROR = "schema_argument_error"
    PERMISSION_DENIED = "permission_denied"
    SEMANTIC_LOOP = "semantic_loop"
    EMPTY_OR_UNHELPFUL_RESULT = "empty_or_unhelpful_result"
    PROMPT_INJECTION_DETECTED = "prompt_injection_detected"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    RUNTIME_EXCEPTION = "runtime_exception"


class RecoveryStrategy(str, Enum):
    NONE = "none"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    SCHEMA_AUTO_REPAIR = "schema_auto_repair"
    TOOL_FALLBACK = "tool_fallback"
    SEMANTIC_LOOP_BREAKER = "semantic_loop_breaker"
    QUERY_EXPANSION = "query_expansion"
    STATE_ROLLBACK = "state_rollback"
    SECURITY_SANITIZATION = "security_sanitization"
    HUMAN_ESCALATION = "human_escalation"


class PolicyDecision(str, Enum):
    ALLOWED = "allowed"
    REQUIRE_APPROVAL = "require_approval"
    BLOCKED = "blocked"


class ToolCallRequest(BaseModel):
    call_id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    raw_response: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class ToolCallResult(BaseModel):
    call_id: str
    tool_name: str
    success: bool
    output: Any = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    is_sandboxed: bool = True
    tainted: bool = False  # Set if output contains potential prompt injection


class SelfHealingEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"heal_{uuid.uuid4().hex[:8]}")
    step_index: int
    failure_type: FailureType
    original_error: str
    recovery_strategy: RecoveryStrategy
    action_taken: str
    recovered: bool = False
    recovery_time_ms: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class StepTrace(BaseModel):
    step_index: int
    phase: ExecutionPhase
    thought: Optional[str] = None
    tool_call: Optional[ToolCallRequest] = None
    policy_decision: Optional[PolicyDecision] = None
    policy_reason: Optional[str] = None
    tool_result: Optional[ToolCallResult] = None
    healing_events: List[SelfHealingEvent] = Field(default_factory=list)
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    duration_ms: float = 0.0
    timestamp: float = Field(default_factory=time.time)


class SubTask(BaseModel):
    id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:6]}")
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_tool: Optional[str] = None
    result: Optional[str] = None


class Checkpoint(BaseModel):
    checkpoint_id: str = Field(default_factory=lambda: f"chk_{uuid.uuid4().hex[:8]}")
    step_index: int
    state_snapshot: Dict[str, Any]
    timestamp: float = Field(default_factory=time.time)


class PendingApproval(BaseModel):
    approval_id: str = Field(default_factory=lambda: f"appr_{uuid.uuid4().hex[:8]}")
    task_id: str
    tool_name: str
    arguments: Dict[str, Any]
    risk_level: str = "HIGH"
    reason: str
    timestamp: float = Field(default_factory=time.time)


class AgentState(BaseModel):
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    current_phase: ExecutionPhase = ExecutionPhase.PLANNING
    current_step: int = 0
    plan: List[SubTask] = Field(default_factory=list)
    history: List[StepTrace] = Field(default_factory=list)
    checkpoints: List[Checkpoint] = Field(default_factory=list)
    working_memory: Dict[str, Any] = Field(default_factory=dict)
    
    # Observability & Metrics
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    total_duration_ms: float = 0.0
    
    # Self-Healing Metrics
    failure_count: int = 0
    recovered_count: int = 0
    healing_events: List[SelfHealingEvent] = Field(default_factory=list)
    
    # Approvals
    pending_approval: Optional[PendingApproval] = None
    final_output: Optional[str] = None
    error: Optional[str] = None
