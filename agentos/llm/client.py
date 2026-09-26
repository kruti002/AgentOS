"""
OpenAI-compatible LLM client for AgentOS.

Talks to any OpenAI-compatible endpoint (FreeLLMAPI by default) using the
official `openai` SDK. Centralizes:
  - configuration (base_url / api_key / model) from agentos.config.settings
  - real token usage extraction
  - JSON-mode helpers for structured planning output
  - graceful degradation: when no key is configured or the endpoint is
    unreachable, calls raise LLMUnavailable so callers can fall back.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import json
import re

from agentos.config import settings

try:
    from openai import OpenAI
    _OPENAI_IMPORTED = True
except Exception:  # pragma: no cover - openai should be installed
    OpenAI = None  # type: ignore
    _OPENAI_IMPORTED = False


class LLMUnavailable(RuntimeError):
    """Raised when the LLM cannot be used (unconfigured or unreachable)."""


def _is_connection_error(exc: Exception) -> bool:
    """Best-effort detection of transport/connection failures."""
    name = type(exc).__name__.lower()
    if "connect" in name or "timeout" in name:
        return True
    msg = str(exc).lower()
    return any(
        s in msg
        for s in ("connection error", "connection refused", "failed to establish",
                  "max retries", "timed out", "getaddrinfo", "name or service")
    )


def _estimate_tokens(text: str) -> int:
    """Rough token estimate for providers that omit usage (~4 chars/token)."""
    if not text:
        return 0
    return max(1, round(len(text) / 4))


class LLMUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False  # True when derived from text length, not provider-reported


class LLMToolCall(BaseModel):
    """A tool call requested by the model via native function-calling."""
    id: str
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: LLMUsage = Field(default_factory=LLMUsage)
    routed_via: Optional[str] = None  # X-Routed-Via header from FreeLLMAPI, if present
    tool_calls: List[LLMToolCall] = Field(default_factory=list)
    finish_reason: Optional[str] = None


class LLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = base_url or settings.llm_base_url
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.default_model
        self.timeout = timeout if timeout is not None else settings.timeout_seconds
        self._client = None
        # Once a transport error is seen, stop attempting network calls for the
        # rest of the process so repeated failures (e.g. a benchmark loop
        # against an offline router) don't each pay the full timeout.
        self._endpoint_down = False
        # Hard opt-out: when True the client reports unavailable and never calls
        # the network. Used to force deterministic, fast heuristic runs.
        self.disabled = False

    @property
    def available(self) -> bool:
        """True when the SDK is importable, a real key is set, endpoint is up."""
        if self.disabled:
            return False
        return _OPENAI_IMPORTED and settings.llm_configured and not self._endpoint_down

    def _get_client(self):
        if self._endpoint_down:
            raise LLMUnavailable("LLM endpoint previously unreachable this run.")
        if self._client is None:
            if not _OPENAI_IMPORTED:
                raise LLMUnavailable("The 'openai' package is not installed.")
            if not settings.llm_configured:
                raise LLMUnavailable(
                    "No LLM API key configured. Set FREELLM_API_KEY in .env."
                )
            # api_key must be non-empty for the SDK; the router validates it.
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key or "unset",
                timeout=self.timeout,
                max_retries=0,
            )
        return self._client

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send a chat completion. Raises LLMUnavailable on config/transport errors."""
        client = self._get_client()
        use_model = model or self.model

        kwargs: Dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            # Best-effort structured output; not every free provider honors it,
            # so callers should still parse defensively.
            kwargs["response_format"] = {"type": "json_object"}

        try:
            completion = client.chat.completions.create(**kwargs)
        except Exception as e:
            # Mark endpoint as down on connection/transport errors so the rest
            # of the run short-circuits instead of retrying a dead endpoint.
            if _is_connection_error(e):
                self._endpoint_down = True
            raise LLMUnavailable(f"LLM request failed: {e}") from e

        choice = completion.choices[0]
        content = choice.message.content or ""
        usage = self._build_usage(completion, messages, content)

        return LLMResponse(
            content=content,
            model=getattr(completion, "model", use_model) or use_model,
            usage=usage,
            finish_reason=getattr(choice, "finish_reason", None),
        )

    @staticmethod
    def _build_usage(completion: Any, messages: List[Dict[str, Any]], content: str) -> "LLMUsage":
        """Extract token usage, deriving/estimating when the provider omits it."""
        usage = LLMUsage()
        if getattr(completion, "usage", None):
            usage = LLMUsage(
                prompt_tokens=getattr(completion.usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(completion.usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(completion.usage, "total_tokens", 0) or 0,
            )
        if usage.total_tokens == 0 and (usage.prompt_tokens or usage.completion_tokens):
            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        if usage.total_tokens == 0:
            prompt_text = "".join(str(m.get("content", "")) for m in messages)
            usage = LLMUsage(
                prompt_tokens=_estimate_tokens(prompt_text),
                completion_tokens=_estimate_tokens(content),
                total_tokens=0,
                estimated=True,
            )
            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        return usage

    def supports_tools(self) -> bool:
        """Whether native tool-calling should be attempted (endpoint reachable)."""
        return self.available

    def embed(self, texts: List[str], model: Optional[str] = None) -> Optional[List[List[float]]]:
        """Return embedding vectors for texts, or None if embeddings are unavailable."""
        if not self.available:
            return None
        client = self._get_client()
        use_model = model or getattr(settings, "embedding_model", "text-embedding-3-small")
        try:
            resp = client.embeddings.create(model=use_model, input=texts)
            return [d.embedding for d in resp.data]
        except Exception:
            # Endpoint may not serve embeddings on the free tier; degrade.
            return None

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Chat with native OpenAI tool-calling.

        `tools` is a list of JSON-schema tool definitions (as produced by the
        MCP registry). Returns an LLMResponse whose `tool_calls` holds any tool
        calls the model requested. Raises LLMUnavailable on transport errors.
        """
        client = self._get_client()
        use_model = model or self.model

        # Wrap each tool schema in the OpenAI function-tool envelope.
        openai_tools = [{"type": "function", "function": t} for t in tools]

        kwargs: Dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "tools": openai_tools,
            "tool_choice": "auto",
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            completion = client.chat.completions.create(**kwargs)
        except Exception as e:
            if _is_connection_error(e):
                self._endpoint_down = True
            raise LLMUnavailable(f"LLM tool request failed: {e}") from e

        choice = completion.choices[0]
        message = choice.message
        content = message.content or ""

        tool_calls: List[LLMToolCall] = []
        for tc in (getattr(message, "tool_calls", None) or []):
            fn = getattr(tc, "function", None)
            if fn is None:
                continue
            raw_args = getattr(fn, "arguments", "") or "{}"
            parsed_args = self._extract_json(raw_args)
            if not isinstance(parsed_args, dict):
                parsed_args = {}
            tool_calls.append(
                LLMToolCall(
                    id=getattr(tc, "id", "") or f"call_{len(tool_calls)}",
                    name=getattr(fn, "name", "") or "",
                    arguments=parsed_args,
                )
            )

        usage = self._build_usage(completion, messages, content)
        return LLMResponse(
            content=content,
            model=getattr(completion, "model", use_model) or use_model,
            usage=usage,
            tool_calls=tool_calls,
            finish_reason=getattr(choice, "finish_reason", None),
        )

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        on_delta: Optional[Any] = None,
    ) -> LLMResponse:
        """Stream a chat completion, invoking on_delta(text) for each chunk.

        Returns the assembled LLMResponse. Falls back to a non-streaming call
        if streaming isn't supported by the endpoint.
        """
        client = self._get_client()
        use_model = model or self.model
        kwargs: Dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            stream = client.chat.completions.create(**kwargs)
            parts: List[str] = []
            for chunk in stream:
                try:
                    delta = chunk.choices[0].delta
                    piece = getattr(delta, "content", None)
                except (IndexError, AttributeError):
                    piece = None
                if piece:
                    parts.append(piece)
                    if on_delta is not None:
                        on_delta(piece)
            content = "".join(parts)
        except Exception as e:
            if _is_connection_error(e):
                self._endpoint_down = True
            raise LLMUnavailable(f"LLM stream failed: {e}") from e

        # Streamed responses usually omit usage; estimate from text.
        usage = LLMUsage(
            prompt_tokens=_estimate_tokens("".join(str(m.get("content", "")) for m in messages)),
            completion_tokens=_estimate_tokens(content),
            estimated=True,
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        return LLMResponse(content=content, model=use_model, usage=usage)

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> tuple[Any, LLMResponse]:
        """Chat and parse the response as JSON. Returns (parsed_or_None, response)."""
        response = self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        parsed = self._extract_json(response.content)
        return parsed, response

    @staticmethod
    def _extract_json(text: str) -> Optional[Any]:
        """Robustly extract a JSON object/array from a model response."""
        if not text:
            return None
        candidate = text.strip()

        # Strip markdown code fences if present.
        if "```" in candidate:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", candidate)
            if match:
                candidate = match.group(1).strip()

        # Direct parse.
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Fall back to the first balanced {...} or [...] span, preferring
        # whichever opening bracket appears first in the text.
        obj_start = candidate.find("{")
        arr_start = candidate.find("[")
        order: List[tuple[str, str]] = []
        if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
            order = [("[", "]"), ("{", "}")]
        else:
            order = [("{", "}"), ("[", "]")]

        for open_ch, close_ch in order:
            start = candidate.find(open_ch)
            end = candidate.rfind(close_ch)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(candidate[start : end + 1])
                except json.JSONDecodeError:
                    continue
        return None


# Global default client instance.
global_llm = LLMClient()
