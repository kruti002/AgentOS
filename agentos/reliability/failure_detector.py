"""
Failure Detector and Anomaly Classifier.
"""

from typing import Optional, Dict, Any
import re
from agentos.runtime.state import FailureType, RecoveryStrategy, ToolCallResult


class FailureDetector:
    def __init__(self):
        # Transient error indicators
        self.transient_patterns = [
            r"timeout", r"timed out", r"connection reset", r"503", r"502", r"504",
            r"rate limit", r"too many requests", r"429", r"temporarily unavailable",
            r"remote disconnected", r"deadline exceeded"
        ]
        
        # Schema error indicators
        self.schema_patterns = [
            r"missing required parameter", r"unexpected argument", r"invalid literal for int",
            r"jsondecodeerror", r"expected string or bytes-like object", r"typeerror",
            r"validation error", r"keyerror", r"could not convert string to float"
        ]

        # Permission indicators
        self.permission_patterns = [
            r"permission denied", r"prohibited", r"blocked by", r"403", r"access denied",
            r"unauthorized"
        ]

    def classify_tool_result(self, result: ToolCallResult) -> tuple[FailureType, RecoveryStrategy]:
        """Classify a tool call failure and recommend optimal recovery strategy."""
        if result.success:
            # Check for empty/unhelpful output
            if result.output is None or result.output == "" or result.output == [] or result.output == {}:
                return FailureType.EMPTY_OR_UNHELPFUL_RESULT, RecoveryStrategy.QUERY_EXPANSION
            if isinstance(result.output, dict) and result.output.get("total_results") == 0:
                return FailureType.EMPTY_OR_UNHELPFUL_RESULT, RecoveryStrategy.QUERY_EXPANSION
            if result.tainted:
                return FailureType.PROMPT_INJECTION_DETECTED, RecoveryStrategy.SECURITY_SANITIZATION
            return FailureType.NONE, RecoveryStrategy.NONE

        err = (result.error_message or "").lower()

        # 1. Transient API Error
        for p in self.transient_patterns:
            if re.search(p, err):
                return FailureType.TRANSIENT_API_ERROR, RecoveryStrategy.EXPONENTIAL_BACKOFF

        # 2. Schema / Argument Error
        for p in self.schema_patterns:
            if re.search(p, err):
                return FailureType.SCHEMA_ARGUMENT_ERROR, RecoveryStrategy.SCHEMA_AUTO_REPAIR

        # 3. Permission Denied
        for p in self.permission_patterns:
            if re.search(p, err):
                return FailureType.PERMISSION_DENIED, RecoveryStrategy.TOOL_FALLBACK

        # 4. Fallback runtime exception
        return FailureType.RUNTIME_EXCEPTION, RecoveryStrategy.TOOL_FALLBACK
