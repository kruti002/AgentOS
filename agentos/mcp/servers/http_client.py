"""
HTTP Client MCP Server. Makes real outbound HTTP requests with limits.
"""

from typing import Dict, Any, Optional
import json
import httpx

from agentos.mcp.servers.base import BaseMCPServer
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter


_MAX_BODY_BYTES = 1_000_000  # cap response body at ~1 MB


class HTTPClientMCPServer(BaseMCPServer):
    def __init__(self, timeout_seconds: float = 10.0):
        super().__init__(name="http_client_mcp")
        self.timeout = timeout_seconds

    def http_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request and return status, headers, and (capped) body."""
        target = (url or "").strip()
        if not target.lower().startswith(("http://", "https://")):
            target = "https://" + target
        m = (method or "GET").upper()
        if m not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
            raise ValueError(f"Unsupported HTTP method: {m}")

        req_headers = headers or {}
        content = body.encode("utf-8") if isinstance(body, str) else None

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.request(m, target, headers=req_headers, content=content)
                raw = resp.content[:_MAX_BODY_BYTES]
                text = raw.decode(resp.encoding or "utf-8", errors="replace")
        except Exception as e:
            return {"url": target, "method": m, "status_code": 0, "error": str(e), "body": ""}

        return {
            "url": target,
            "method": m,
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": text,
            "truncated": len(resp.content) > _MAX_BODY_BYTES,
        }

    def register_tools(self, registry: ToolRegistry) -> None:
        registry.register(ToolDefinition(
            name="http_request",
            description="Make an outbound HTTP request (GET/POST/etc.) and return the response.",
            category="web",
            risk_level="MEDIUM",
            parameters={
                "url": ToolParameter(name="url", type="string", description="Request URL"),
                "method": ToolParameter(name="method", type="string", description="HTTP method (default GET)", required=False, default="GET"),
                "headers": ToolParameter(name="headers", type="object", description="Optional request headers", required=False),
                "body": ToolParameter(name="body", type="string", description="Optional request body", required=False),
            },
            handler=self.http_request,
        ))
