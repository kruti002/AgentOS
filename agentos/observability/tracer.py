"""
OpenTelemetry Tracing and Waterfall Span Collector.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import time
import uuid
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter


class TraceSpan(BaseModel):
    span_id: str = Field(default_factory=lambda: f"span_{uuid.uuid4().hex[:8]}")
    parent_span_id: Optional[str] = None
    name: str
    category: str  # "llm", "tool", "security", "healing", "orchestrator"
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    status: str = "OK"  # "OK", "ERROR", "RECOVERED"
    attributes: Dict[str, Any] = Field(default_factory=dict)
    events: List[Dict[str, Any]] = Field(default_factory=list)


class OpenTelemetryTracer:
    def __init__(self, service_name: str = "agentos-runtime"):
        self.service_name = service_name
        self._provider = TracerProvider()
        trace.set_tracer_provider(self._provider)
        self._tracer = trace.get_tracer("agentos.tracer", "0.1.0")
        self.recorded_spans: List[TraceSpan] = []
        self.otlp_enabled: bool = False
        self._maybe_enable_otlp()

    def _maybe_enable_otlp(self) -> None:
        """Attach an OTLP span exporter when AGENTOS_OTLP_ENDPOINT is set.

        Fails gracefully if the OTLP exporter package isn't installed or the
        endpoint is invalid, so tracing always works in-memory regardless.
        """
        import os

        endpoint = os.getenv("AGENTOS_OTLP_ENDPOINT", "").strip()
        if not endpoint:
            return
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            exporter = OTLPSpanExporter(endpoint=endpoint)
            self._provider.add_span_processor(BatchSpanProcessor(exporter))
            self.otlp_enabled = True
        except Exception:
            # OTLP exporter not installed or misconfigured; keep in-memory only.
            self.otlp_enabled = False

    def start_span(
        self,
        name: str,
        category: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> TraceSpan:
        """Create and track a new execution span."""
        span = TraceSpan(
            name=name,
            category=category,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
            start_time=time.time()
        )
        self.recorded_spans.append(span)
        return span

    def end_span(self, span: TraceSpan, status: str = "OK", error: Optional[str] = None) -> TraceSpan:
        """Finalize a span with duration calculation and status."""
        span.end_time = time.time()
        span.duration_ms = (span.end_time - span.start_time) * 1000
        span.status = status
        if error:
            span.attributes["error.message"] = error
            span.events.append({
                "name": "exception",
                "timestamp": time.time(),
                "attributes": {"exception.message": error}
            })
        self._export_otlp(span, error)
        return span

    def _export_otlp(self, span: TraceSpan, error: Optional[str]) -> None:
        """Emit a real OpenTelemetry span to the configured OTLP exporter."""
        if not self.otlp_enabled:
            return
        try:
            from opentelemetry.trace import Status, StatusCode

            start_ns = int(span.start_time * 1e9)
            end_ns = int((span.end_time or time.time()) * 1e9)
            otel_span = self._tracer.start_span(span.name, start_time=start_ns)
            otel_span.set_attribute("agentos.category", span.category)
            for k, v in (span.attributes or {}).items():
                try:
                    otel_span.set_attribute(f"agentos.{k}", v if isinstance(v, (str, int, float, bool)) else str(v))
                except Exception:
                    pass
            if error:
                otel_span.set_status(Status(StatusCode.ERROR, error))
            otel_span.end(end_time=end_ns)
        except Exception:
            pass

    def add_span_event(self, span: TraceSpan, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add a point-in-time event inside a span."""
        span.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {}
        })

    def get_trace_tree(self) -> List[Dict[str, Any]]:
        """Return the spans organized as a hierarchical tree suitable for waterfall DAG rendering."""
        lookup = {s.span_id: s.model_dump() for s in self.recorded_spans}
        root_nodes = []

        for span_data in lookup.values():
            span_data["children"] = []

        for span_data in lookup.values():
            parent_id = span_data.get("parent_span_id")
            if parent_id and parent_id in lookup:
                lookup[parent_id]["children"].append(span_data)
            else:
                root_nodes.append(span_data)

        return root_nodes

    def get_task_spans(self, task_id: str) -> List[Dict[str, Any]]:
        """Return the span subtree for a task as a hierarchical tree.

        Finds the task's root span (whose attributes carry task_id, or whose
        name ends with the task_id) and all of its descendants, then nests them.
        """
        root = next(
            (s for s in self.recorded_spans
             if s.attributes.get("task_id") == task_id or s.name.endswith(task_id)),
            None,
        )
        if root is None:
            return []

        keep = {root.span_id}
        changed = True
        while changed:
            changed = False
            for s in self.recorded_spans:
                if s.parent_span_id in keep and s.span_id not in keep:
                    keep.add(s.span_id)
                    changed = True

        lookup = {s.span_id: s.model_dump() for s in self.recorded_spans if s.span_id in keep}
        for data in lookup.values():
            data["children"] = []
        roots: List[Dict[str, Any]] = []
        for data in lookup.values():
            parent_id = data.get("parent_span_id")
            if parent_id and parent_id in lookup:
                lookup[parent_id]["children"].append(data)
            else:
                roots.append(data)
        return roots

    def clear(self) -> None:
        self.recorded_spans.clear()


# Global default tracer
global_tracer = OpenTelemetryTracer()
