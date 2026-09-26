"""
Persistence layer for AgentOS.

Stores task summaries, trace spans, and metric records in an embedded DuckDB
database so history survives process restarts.
"""

from agentos.storage.store import PersistentStore, global_store

__all__ = ["PersistentStore", "global_store"]
