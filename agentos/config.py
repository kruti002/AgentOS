"""
Global configuration settings for AgentOS.
"""

from pydantic import BaseModel, Field
import os
from pathlib import Path

# Load variables from a local .env file (if present) into the process
# environment before settings are read. Never fails if python-dotenv is
# missing or the file is absent.
try:
    from dotenv import load_dotenv

    _ENV_PATH = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=_ENV_PATH)
except Exception:
    pass


class AgentOSConfig(BaseModel):
    # System settings
    app_name: str = "AgentOS"
    version: str = "0.1.0"
    debug: bool = True
    workspace_root: str = Field(default_factory=lambda: str(Path(__file__).parent.parent))
    sandbox_dir: str = Field(default_factory=lambda: str(Path(__file__).parent.parent / "sandbox_workspace"))

    # LLM provider (FreeLLMAPI / any OpenAI-compatible endpoint)
    llm_base_url: str = Field(default_factory=lambda: os.getenv("FREELLM_BASE_URL", "http://localhost:3001/v1"))
    llm_api_key: str = Field(default_factory=lambda: os.getenv("FREELLM_API_KEY", ""))

    # API hardening
    # Bearer token required on API requests. When empty, auth is disabled
    # (open for local development).
    auth_token: str = Field(default_factory=lambda: os.getenv("AGENTOS_AUTH_TOKEN", ""))
    # Comma-separated allowed CORS origins. "*" allows all (dev default).
    allowed_origins_raw: str = Field(default_factory=lambda: os.getenv("AGENTOS_ALLOWED_ORIGINS", "*"))
    # Simple fixed-window rate limit per client IP (requests per window seconds).
    rate_limit_requests: int = Field(default_factory=lambda: int(os.getenv("AGENTOS_RATE_LIMIT", "120")))
    rate_limit_window_seconds: float = Field(default_factory=lambda: float(os.getenv("AGENTOS_RATE_WINDOW", "60")))

    # Model defaults
    default_model: str = Field(default_factory=lambda: os.getenv("AGENTOS_MODEL", "auto"))
    embedding_model: str = Field(default_factory=lambda: os.getenv("AGENTOS_EMBEDDING_MODEL", "text-embedding-3-small"))
    fallback_model: str = "gpt-4o-mini"
    max_iterations: int = 25
    max_tool_retries: int = 3
    timeout_seconds: float = 60.0
    
    # Observability
    enable_otel: bool = True
    service_name: str = "agentos-runtime"
    trace_sample_rate: float = 1.0
    
    # Cost Tracker Rates (USD per 1M tokens) - input/output
    cost_rates: dict = {
        "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.5-pro": {"input": 1.25, "output": 5.00},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    }
    # Fallback rate (USD per 1M tokens) for unknown or routed ("auto") models.
    default_cost_rate: dict = {"input": 0.10, "output": 0.30}
    
    # Security Policies
    enforce_sandbox: bool = True
    allow_network_search: bool = True
    require_human_approval_for_destructive: bool = True
    max_file_read_bytes: int = 1024 * 1024 * 10  # 10MB
    
    # Self-Healing Thresholds
    loop_detection_window: int = 4
    loop_similarity_threshold: float = 0.85
    exponential_backoff_base: float = 0.5
    max_backoff_seconds: float = 5.0


    @property
    def llm_configured(self) -> bool:
        """True when a usable LLM API key is present."""
        key = (self.llm_api_key or "").strip()
        return bool(key) and key != "freellmapi-your-unified-key-here"

    @property
    def auth_enabled(self) -> bool:
        """True when a non-empty auth token is configured."""
        return bool((self.auth_token or "").strip())

    @property
    def allowed_origins(self) -> list:
        """Parsed list of allowed CORS origins."""
        raw = (self.allowed_origins_raw or "*").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


# Global singleton instance
settings = AgentOSConfig()
