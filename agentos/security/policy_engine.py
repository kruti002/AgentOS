"""
Security Policy Engine. Validates tool calls and actions against permission matrices.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import re
from agentos.runtime.state import PolicyDecision, ToolCallRequest
from agentos.observability.metrics import global_metrics


class PolicyRule(BaseModel):
    rule_id: str
    description: str
    target_tools: List[str] = Field(default_factory=list)  # Empty means all tools
    decision: PolicyDecision
    condition: Optional[str] = None  # Python eval expression or regex pattern


class SecurityPolicyEngine:
    def __init__(self):
        self.rules: List[PolicyRule] = []
        self._init_default_policy()

    def _init_default_policy(self):
        """Standard production security policy matrix."""
        # Critical blocks
        self.rules.append(PolicyRule(
            rule_id="BLOCK_ROOT_DESTRUCTION",
            description="Block destructive system disk wiping or recursive root deletion",
            target_tools=["shell_exec"],
            decision=PolicyDecision.BLOCKED,
            condition=r"(rm\s+-rf\s+/|format\s+[c-z]:|rmdir\s+/s\s+/q)"
        ))
        
        self.rules.append(PolicyRule(
            rule_id="BLOCK_SECRET_ENV_ACCESS",
            description="Block reading private SSH keys or environment secrets",
            target_tools=["fs_read", "shell_exec"],
            decision=PolicyDecision.BLOCKED,
            condition=r"(\.ssh/id_rsa|\.env|id_ed25519|passwd|shadow)"
        ))

        # Human-in-the-loop approvals
        self.rules.append(PolicyRule(
            rule_id="REQUIRE_APPROVAL_SHELL",
            description="Require human approval before running arbitrary shell commands",
            target_tools=["shell_exec"],
            decision=PolicyDecision.REQUIRE_APPROVAL
        ))

        self.rules.append(PolicyRule(
            rule_id="REQUIRE_APPROVAL_PY_EXEC",
            description="Require human approval before executing arbitrary Python code",
            target_tools=["py_exec"],
            decision=PolicyDecision.REQUIRE_APPROVAL
        ))

        self.rules.append(PolicyRule(
            rule_id="REQUIRE_APPROVAL_FILE_OVERWRITE",
            description="Require approval when overwriting existing critical files",
            target_tools=["fs_write"],
            decision=PolicyDecision.REQUIRE_APPROVAL,
            condition=r"(\.config|\.git|pyproject\.toml|package\.json)"
        ))

    def evaluate(self, request: ToolCallRequest, context: Optional[Dict[str, Any]] = None) -> tuple[PolicyDecision, str]:
        """Evaluate a tool invocation against policy rules."""
        tool_name = request.tool_name
        args_str = str(request.arguments)

        # Check explicit rules
        for rule in self.rules:
            if not rule.target_tools or tool_name in rule.target_tools:
                if rule.condition:
                    if re.search(rule.condition, args_str, re.IGNORECASE):
                        if rule.decision == PolicyDecision.BLOCKED:
                            global_metrics.record_security_block()
                        return rule.decision, f"Rule [{rule.rule_id}]: {rule.description}"
                else:
                    # Target matches unconditional rule
                    return rule.decision, f"Rule [{rule.rule_id}]: {rule.description}"

        # Default fallback: allow low-risk operations
        return PolicyDecision.ALLOWED, "Default policy: Allowed"
