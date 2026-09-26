"""
Benchmark execution and comparison API routes.
"""

from fastapi import APIRouter, BackgroundTasks
from typing import Optional, Dict, Any, List
from agentos.evaluation.benchmark_runner import BenchmarkRunner
from agentos.evaluation.datasets.benchmark_tasks import BENCHMARK_SUITE_100, CATEGORIES
from agentos.evaluation.metrics_calculator import BenchmarkComparisonReport

router = APIRouter(prefix="/api/benchmark", tags=["Benchmark"])

# In-memory cached report
cached_benchmark_report: Optional[Dict[str, Any]] = None
is_benchmark_running: bool = False


@router.get("/tasks")
async def list_benchmark_tasks():
    """List available benchmark task scenarios."""
    return {
        "total_tasks": len(BENCHMARK_SUITE_100),
        "categories": CATEGORIES,
        "tasks": BENCHMARK_SUITE_100
    }


@router.post("/run")
async def trigger_benchmark_run(limit: int = 20):
    """Run comparative benchmark suite and return live report."""
    global cached_benchmark_report, is_benchmark_running
    is_benchmark_running = True
    runner = BenchmarkRunner()
    
    report = await runner.run_full_suite(limit=limit)
    cached_benchmark_report = report.model_dump()
    is_benchmark_running = False
    
    return cached_benchmark_report


@router.get("/results")
async def get_benchmark_results():
    """Get latest cached benchmark report or run a default 10-task preview."""
    global cached_benchmark_report
    if cached_benchmark_report is None:
        runner = BenchmarkRunner()
        report = await runner.run_full_suite(limit=10)
        cached_benchmark_report = report.model_dump()
        
    return cached_benchmark_report
