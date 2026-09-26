"""
AgentOS Benchmark and Evaluation Suite.

Imports are lazy to avoid a circular import: the runtime orchestrator depends on
``fault_injector`` (a submodule here), while ``benchmark_runner`` depends on the
orchestrator. Eagerly importing BenchmarkRunner at package import time would
close that cycle, so we expose the public names lazily via ``__getattr__``.
"""

from typing import Any

__all__ = [
    "BenchmarkRunner",
    "ComparativeEvaluator",
    "BENCHMARK_SUITE_100",
    "QualityEvaluator",
    "DEFAULT_QUALITY_CASES",
]


def __getattr__(name: str) -> Any:
    if name == "BenchmarkRunner":
        from agentos.evaluation.benchmark_runner import BenchmarkRunner
        return BenchmarkRunner
    if name == "ComparativeEvaluator":
        from agentos.evaluation.metrics_calculator import ComparativeEvaluator
        return ComparativeEvaluator
    if name == "BENCHMARK_SUITE_100":
        from agentos.evaluation.datasets.benchmark_tasks import BENCHMARK_SUITE_100
        return BENCHMARK_SUITE_100
    if name in ("QualityEvaluator", "DEFAULT_QUALITY_CASES"):
        from agentos.evaluation import quality_eval
        return getattr(quality_eval, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
