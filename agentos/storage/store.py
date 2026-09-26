"""
DuckDB-backed persistent store for AgentOS task history, traces, and metrics.

Designed to be safe and non-fatal: if the database cannot be opened or a write
fails, the store logs nothing and simply becomes a no-op so it never breaks a
task run. State in AgentOS remains authoritative in memory; this store is an
additive durable record.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import threading
import time

import duckdb

from agentos.config import settings


class PersistentStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(Path(settings.workspace_root) / "agentos_history.duckdb")
        self._lock = threading.Lock()
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self.enabled = True
        try:
            self._conn = duckdb.connect(self.db_path)
            self._init_schema()
        except Exception:
            # If persistence can't initialize, degrade to a no-op store.
            self._conn = None
            self.enabled = False

    def _init_schema(self) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id VARCHAR PRIMARY KEY,
                goal VARCHAR,
                status VARCHAR,
                final_output VARCHAR,
                total_steps INTEGER,
                total_tokens INTEGER,
                total_prompt_tokens INTEGER,
                total_completion_tokens INTEGER,
                total_cost_usd DOUBLE,
                duration_ms DOUBLE,
                failure_count INTEGER,
                recovered_count INTEGER,
                model VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spans (
                span_id VARCHAR,
                task_id VARCHAR,
                parent_span_id VARCHAR,
                name VARCHAR,
                category VARCHAR,
                status VARCHAR,
                duration_ms DOUBLE,
                attributes VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                task_id VARCHAR,
                success BOOLEAN,
                duration_ms DOUBLE,
                tokens_used INTEGER,
                cost_usd DOUBLE,
                failures_count INTEGER,
                recovered_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    # ------------------------------------------------------------------ #
    def save_task(self, state: Any, model: str = "") -> None:
        """Persist a task summary (upsert by task_id)."""
        if not self.enabled or self._conn is None:
            return
        try:
            with self._lock:
                self._conn.execute("DELETE FROM tasks WHERE task_id = ?", [state.task_id])
                self._conn.execute(
                    "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)",
                    [
                        state.task_id,
                        state.goal,
                        state.status.value if hasattr(state.status, "value") else str(state.status),
                        (state.final_output or "")[:20000],
                        len(state.history),
                        state.total_tokens,
                        state.total_prompt_tokens,
                        state.total_completion_tokens,
                        state.total_cost_usd,
                        state.total_duration_ms,
                        state.failure_count,
                        state.recovered_count,
                        model,
                    ],
                )
        except Exception:
            pass

    def save_spans(self, task_id: str, spans: List[Any]) -> None:
        """Persist trace spans for a task."""
        if not self.enabled or self._conn is None:
            return
        try:
            with self._lock:
                for s in spans:
                    self._conn.execute(
                        "INSERT INTO spans VALUES (?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)",
                        [
                            getattr(s, "span_id", None),
                            task_id,
                            getattr(s, "parent_span_id", None),
                            getattr(s, "name", None),
                            getattr(s, "category", None),
                            getattr(s, "status", None),
                            getattr(s, "duration_ms", 0.0),
                            json.dumps(getattr(s, "attributes", {}) or {}),
                        ],
                    )
        except Exception:
            pass

    def save_metric(
        self,
        task_id: str,
        success: bool,
        duration_ms: float,
        tokens_used: int,
        cost_usd: float,
        failures_count: int,
        recovered_count: int,
    ) -> None:
        if not self.enabled or self._conn is None:
            return
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO metrics VALUES (?,?,?,?,?,?,?, CURRENT_TIMESTAMP)",
                    [task_id, success, duration_ms, tokens_used, cost_usd, failures_count, recovered_count],
                )
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.enabled or self._conn is None:
            return []
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT task_id, goal, status, total_steps, total_tokens, total_cost_usd, "
                    "duration_ms, failure_count, recovered_count, model, created_at "
                    "FROM tasks ORDER BY created_at DESC LIMIT ?",
                    [limit],
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            return []

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled or self._conn is None:
            return None
        try:
            with self._lock:
                cur = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", [task_id])
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
        except Exception:
            return None

    def history_summary(self) -> Dict[str, Any]:
        """Aggregate metrics across all persisted tasks."""
        if not self.enabled or self._conn is None:
            return {"persisted": False}
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),0), "
                    "COALESCE(SUM(total_tokens),0), COALESCE(SUM(total_cost_usd),0.0), "
                    "COALESCE(AVG(duration_ms),0.0) FROM tasks"
                ).fetchone()
            total, completed, tokens, cost, avg_ms = row
            return {
                "persisted": True,
                "total_tasks": int(total),
                "completed_tasks": int(completed),
                "total_tokens": int(tokens),
                "total_cost_usd": round(float(cost), 6),
                "avg_duration_ms": round(float(avg_ms), 2),
            }
        except Exception:
            return {"persisted": False}


# Global store instance
global_store = PersistentStore()
