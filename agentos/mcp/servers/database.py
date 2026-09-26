"""
Database & Analytics MCP Server using embedded DuckDB.
"""

from typing import Dict, Any, List, Optional
import duckdb
from agentos.mcp.servers.base import BaseMCPServer
from agentos.mcp.registry import ToolRegistry, ToolDefinition, ToolParameter


class DatabaseMCPServer(BaseMCPServer):
    def __init__(self, db_path: str = ":memory:"):
        super().__init__(name="database_mcp")
        self.conn = duckdb.connect(db_path)
        self._init_sample_tables()

    def _init_sample_tables(self):
        """Create sample analytical datasets for testing and benchmarks."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY,
                service_name VARCHAR,
                cpu_usage DOUBLE,
                memory_mb INTEGER,
                latency_ms DOUBLE,
                status VARCHAR,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Populate initial rows if empty
        count = self.conn.execute("SELECT COUNT(*) FROM system_metrics").fetchone()[0]
        if count == 0:
            self.conn.execute("""
                INSERT INTO system_metrics (id, service_name, cpu_usage, memory_mb, latency_ms, status) VALUES
                (1, 'api-gateway', 42.5, 512, 18.2, 'HEALTHY'),
                (2, 'auth-service', 18.0, 256, 9.4, 'HEALTHY'),
                (3, 'agent-runtime', 78.4, 2048, 142.6, 'DEGRADED'),
                (4, 'mcp-broker', 12.3, 128, 4.1, 'HEALTHY'),
                (5, 'db-cluster', 65.1, 4096, 45.8, 'HEALTHY');
            """)

    def db_query(self, query: str) -> Dict[str, Any]:
        """Execute a SQL query and return columns and rows."""
        # Clean query
        q = query.strip().rstrip(";")
        
        # Security sanity check: block dangerous operations in basic queries
        forbidden = ["DROP DATABASE", "ATTACH", "INSTALL", "LOAD"]
        for f in forbidden:
            if f in q.upper():
                raise PermissionError(f"Operation '{f}' is prohibited by SQL safety policy.")
                
        cursor = self.conn.cursor()
        cursor.execute(q)
        
        if cursor.description is not None:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            # Convert tuples to list of dicts for friendly consumer JSON
            dict_rows = [dict(zip(columns, row)) for row in rows]
            return {
                "columns": columns,
                "row_count": len(rows),
                "data": dict_rows[:100],  # cap at 100 rows
                "truncated": len(rows) > 100
            }
        else:
            return {"status": "success", "message": "Command executed successfully"}

    def db_schema(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """Inspect schema of all tables or a specific table."""
        if table_name:
            res = self.conn.execute(f"DESCRIBE {table_name}").fetchall()
            cols = [{"column_name": r[0], "data_type": r[1], "nullable": r[2]} for r in res]
            return {"table": table_name, "columns": cols}
        else:
            tables = self.conn.execute("SHOW TABLES").fetchall()
            table_list = [t[0] for t in tables]
            return {"tables": table_list}

    def register_tools(self, registry: ToolRegistry) -> None:
        registry.register(ToolDefinition(
            name="db_query",
            description="Execute analytical SQL query against the database engine.",
            category="database",
            risk_level="MEDIUM",
            parameters={
                "query": ToolParameter(name="query", type="string", description="Valid SQL SELECT or analytical query")
            },
            handler=self.db_query
        ))
        
        registry.register(ToolDefinition(
            name="db_schema",
            description="Inspect available database tables or column specifications.",
            category="database",
            risk_level="LOW",
            parameters={
                "table_name": ToolParameter(name="table_name", type="string", description="Optional specific table name to inspect", required=False)
            },
            handler=self.db_schema
        ))
