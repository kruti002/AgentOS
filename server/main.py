"""
AgentOS FastAPI Main Application.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import logging
import time
import os

# Structured JSON logger for API requests.
_logger = logging.getLogger("agentos.access")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)


def _log_request(method: str, path: str, status: int, duration_ms: float, client: str) -> None:
    try:
        _logger.info(json.dumps({
            "event": "http_request",
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": round(duration_ms, 2),
            "client": client,
            "ts": time.time(),
        }))
    except Exception:
        pass

from server.routes.agent import router as agent_router
from server.routes.stream import router as stream_router
from server.routes.observability import router as obs_router
from server.routes.benchmark import router as benchmark_router
from server.routes.mcp import router as mcp_router
from agentos.runtime.orchestrator import global_orchestrator
from agentos.config import settings

app = FastAPI(
    title="AgentOS Control Plane",
    description="Resilient Agent Runtime, MCP Tool Gateway, Security Sandbox & Self-Healing Platform",
    version="0.1.0"
)

# CORS configuration for frontend (locked to configured origins)
_cors_origins = settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # Credentials cannot be combined with the "*" wildcard per the CORS spec.
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------- #
# Middleware: rate limiting + bearer auth
# ---------------------------------------------------------------------- #

# Paths that never require auth (health, docs, and the static UI).
_PUBLIC_PREFIXES = ("/api/health", "/docs", "/openapi.json", "/redoc")
_rate_state: dict = {}  # client_ip -> (window_start, count)


def _is_api_path(path: str) -> bool:
    return path.startswith("/api/")


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path
    client = request.client.host if request.client else "unknown"
    start = time.time()

    # Rate limiting (per client IP, fixed window) — only for API paths.
    if _is_api_path(path):
        now = time.time()
        window_start, count = _rate_state.get(client, (now, 0))
        if now - window_start >= settings.rate_limit_window_seconds:
            window_start, count = now, 0
        count += 1
        _rate_state[client] = (window_start, count)
        if count > settings.rate_limit_requests:
            _log_request(request.method, path, 429, (time.time() - start) * 1000, client)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Slow down."},
            )

    # Bearer auth — only when a token is configured and only for protected API paths.
    if settings.auth_enabled and _is_api_path(path) and not path.startswith(_PUBLIC_PREFIXES):
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if token != settings.auth_token:
            _log_request(request.method, path, 401, (time.time() - start) * 1000, client)
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid bearer token."},
            )

    response = await call_next(request)
    if _is_api_path(path):
        _log_request(request.method, path, response.status_code, (time.time() - start) * 1000, client)
    return response

# Register API Routers
app.include_router(agent_router)
app.include_router(stream_router)
app.include_router(obs_router)
app.include_router(benchmark_router)
app.include_router(mcp_router)


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AgentOS Runtime",
        "version": settings.version,
        "mcp_tools_count": len(global_orchestrator.mcp_gateway.list_tools()),
        "llm_configured": settings.llm_configured,
        "llm_model": settings.default_model,
        "llm_base_url": settings.llm_base_url,
    }


# Serve built web static files if present
web_dist = Path(__file__).parent.parent / "web" / "dist"
if web_dist.exists() and web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="static")
