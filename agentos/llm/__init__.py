"""
LLM client layer for AgentOS.

Provides a thin, provider-agnostic wrapper around any OpenAI-compatible
endpoint (FreeLLMAPI by default). All model calls in AgentOS go through
this layer so token/cost accounting and graceful fallback are centralized.
"""

from agentos.llm.client import (
    LLMClient,
    LLMResponse,
    LLMUsage,
    LLMToolCall,
    global_llm,
)

__all__ = ["LLMClient", "LLMResponse", "LLMUsage", "LLMToolCall", "global_llm"]
