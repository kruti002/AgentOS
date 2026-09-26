"""
Execution Sandbox and Path Isolation Manager.
"""

from typing import Optional
from pathlib import Path
import os
from agentos.config import settings


class ExecutionSandbox:
    def __init__(self, sandbox_dir: Optional[str] = None):
        self.root = Path(sandbox_dir or settings.sandbox_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def is_safe_path(self, target_path: str) -> bool:
        """Check if a path is contained strictly within the sandbox directory."""
        try:
            p = Path(target_path)
            if not p.is_absolute():
                resolved = (self.root / p).resolve()
            else:
                resolved = p.resolve()
            resolved.relative_to(self.root)
            return True
        except (ValueError, Exception):
            return False

    def sanitize_path(self, target_path: str) -> Path:
        """Coerce an unsafe path to a safe destination inside the sandbox."""
        p = Path(target_path)
        if not p.is_absolute():
            return (self.root / p).resolve()
        try:
            p.resolve().relative_to(self.root)
            return p.resolve()
        except ValueError:
            # Strip absolute root and place in sandbox
            clean_name = p.name
            return (self.root / clean_name).resolve()

    def clean_sandbox(self) -> None:
        """Empty sandbox folder contents."""
        for item in self.root.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                import shutil
                shutil.rmtree(item)
