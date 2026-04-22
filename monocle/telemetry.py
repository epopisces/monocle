"""
monocle/telemetry.py — OpenTelemetry cross-cutting concern.

Usage:
    from monocle.telemetry import configure_telemetry, get_tracer, span, timed

    # In app lifespan (called once):
    configure_telemetry(settings)

    # In any module:
    async def my_func():
        async with span("ingest.step.route", template="person"):
            ...
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from monocle.config import Settings

logger = logging.getLogger(__name__)

# These are module-level placeholders; replaced by real OTel objects after
# configure_telemetry() is called.
_tracer = None
_meter = None
_configured = False


class _RouteFilterSpanProcessor:
    """Span processor that drops spans for configured route prefixes before export.

    The filter list is mutable at runtime — call ``set_filters()`` to update which
    routes are suppressed without restarting the server.  Useful for hiding noisy
    polling endpoints (e.g. ``/api/review/count``) while troubleshooting.
    """

    def __init__(self, wrapped_processor: Any, initial_filters: list[str]) -> None:
        self.wrapped_processor = wrapped_processor
        self._filters: list[str] = list(initial_filters)

    def set_filters(self, filters: list[str]) -> None:
        """Replace the active filter list (thread-safe write; GIL is sufficient)."""
        self._filters = list(filters)

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        self.wrapped_processor.on_start(span, parent_context)

    def on_end(self, span: Any) -> None:
        route = span.attributes.get("http.route", "")
        if any(route.startswith(f) for f in self._filters):
            return
        self.wrapped_processor.on_end(span)

    def _on_ending(self, span: Any) -> None:
        # Required by OTel SDK lifecycle — forward to wrapped processor
        if hasattr(self.wrapped_processor, "_on_ending"):
            self.wrapped_processor._on_ending(span)

    def shutdown(self) -> None:
        self.wrapped_processor.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.wrapped_processor.force_flush(timeout_millis)


# Keep old name as an alias for any external references
_HealthCheckFilterSpanProcessor = _RouteFilterSpanProcessor


def configure_telemetry(settings: "Settings") -> "_RouteFilterSpanProcessor | None":
    """Wire up TracerProvider, MeterProvider, and root-logger handler.

    Returns the ``_RouteFilterSpanProcessor`` instance so callers can update
    the filter list at runtime (e.g. from the settings PATCH endpoint).
    Returns ``None`` when telemetry is disabled or setup fails.
    """
    global _tracer, _meter, _configured

    if not settings.telemetry.enabled:
        logger.info("Telemetry disabled — using no-op tracer/meter")
        _configured = True
        return None

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        resource = Resource.create({SERVICE_NAME: "monocle"})

        # --- Span exporter ---
        if settings.telemetry.otlp_transport == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            span_exporter = OTLPSpanExporter(endpoint=settings.telemetry.otlp_endpoint)
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            span_exporter = OTLPSpanExporter(
                endpoint=f"{settings.telemetry.otlp_endpoint}/v1/traces"
            )

        tracer_provider = TracerProvider(resource=resource)
        batch_processor = BatchSpanProcessor(span_exporter)
        filtered_processor = _RouteFilterSpanProcessor(
            batch_processor,
            initial_filters=list(settings.telemetry.trace_filters),
        )
        tracer_provider.add_span_processor(filtered_processor)
        trace.set_tracer_provider(tracer_provider)

        # --- Metric exporter ---
        if settings.telemetry.otlp_transport == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

            metric_exporter = OTLPMetricExporter(endpoint=settings.telemetry.otlp_endpoint)
        else:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

            metric_exporter = OTLPMetricExporter(
                endpoint=f"{settings.telemetry.otlp_endpoint}/v1/metrics"
            )

        metric_reader = PeriodicExportingMetricReader(metric_exporter)
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        # --- Logs/Events exporter (for AI Toolkit Input/Output columns) ---
        # Note: These are private/experimental APIs (_events, _logs, _log_exporter)
        # and may break across OTel releases. Wrapped in try/except for graceful degradation.
        try:
            from opentelemetry import _events, _logs
            from opentelemetry.sdk._events import EventLoggerProvider
            from opentelemetry.sdk._logs import LoggerProvider
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

            if settings.telemetry.otlp_transport == "grpc":
                from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter as GrpcLogExporter

                log_exporter = GrpcLogExporter(endpoint=settings.telemetry.otlp_endpoint)
            else:
                from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

                log_exporter = OTLPLogExporter(
                    endpoint=f"{settings.telemetry.otlp_endpoint}/v1/logs"
                )

            log_provider = LoggerProvider(resource=resource)
            log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
            _logs.set_logger_provider(log_provider)

            event_logger_provider = EventLoggerProvider()
            _events.set_event_logger_provider(event_logger_provider)
        except (ImportError, AttributeError) as e:
            # Private APIs may not be available in all OTel versions
            logger.warning(
                "OpenTelemetry private logs/events APIs unavailable (%s) — "
                "AI Toolkit Input/Output columns will not be populated. "
                "This is expected if OTel has moved these to public APIs or removed them.",
                type(e).__name__,
            )

        # --- Auto-instrumentations ---
        LoggingInstrumentor().instrument(set_logging_format=True)
        HTTPXClientInstrumentor().instrument()
        # FastAPI instrumentation is applied in main.py after app creation

        _tracer = trace.get_tracer("monocle")
        _meter = metrics.get_meter("monocle")
        _configured = True

        logging.getLogger().setLevel(getattr(logging, settings.telemetry.log_level))
        logger.info(
            "Telemetry configured — OTLP endpoint=%s transport=%s filters=%s",
            settings.telemetry.otlp_endpoint,
            settings.telemetry.otlp_transport,
            settings.telemetry.trace_filters,
        )
        return filtered_processor

    except Exception as exc:  # noqa: BLE001
        logger.warning("Telemetry setup failed (continuing without OTel): %s", exc)
        _configured = True
        return None


def get_tracer(name: str = "monocle"):
    """Return the OTel Tracer for *name*, or a no-op object if not configured."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except Exception:  # noqa: BLE001
        return _NoOpTracer()


def get_meter(name: str = "monocle"):
    """Return the OTel Meter for *name*, or a no-op object if not configured."""
    try:
        from opentelemetry import metrics

        return metrics.get_meter(name)
    except Exception:  # noqa: BLE001
        return _NoOpMeter()


@asynccontextmanager
async def span(name: str, **attrs: Any) -> AsyncIterator[Any]:
    """Async context manager that wraps a coroutine in a child OTel span.

    Usage::

        async with span("ingest.step.route", template="person"):
            result = await route(text)

    Falls back to a no-op context if OTel is unavailable.

    Design note — exception safety
    --------------------------------
    The ``try/except`` is scoped *only* to OTel setup (before the yield).
    If setup fails (OTel unavailable / import error) we yield ``None`` and
    return so the body still runs without tracing.

    Once we have a real span, the ``yield`` lives inside the OTel
    ``with start_as_current_span`` block.  Any exception thrown from the body
    (via ``athrow()``) propagates through that ``with`` block's ``__exit__``,
    which records it on the span and returns ``False`` (does not suppress).
    The exception is then re-raised to the caller — nothing here swallows
    application errors.
    """
    # Phase 1 — OTel setup: errors here must never break application code.
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("monocle")
        span_cm = tracer.start_as_current_span(name)
    except Exception:  # noqa: BLE001
        yield None
        return

    # Phase 2 — yield inside the real span.  Body exceptions propagate through
    # start_as_current_span().__exit__ (recorded + re-raised); no suppression.
    with span_cm as s:
        for k, v in attrs.items():
            s.set_attribute(k, str(v))
        yield s


@asynccontextmanager
async def timed(histogram: Any, **attrs: Any) -> AsyncIterator[None]:
    """Async context manager that records wall-clock duration into an OTel Histogram.

    Usage::

        dur = get_meter().create_histogram("ingest.pipeline_duration", unit="ms")
        async with timed(dur, source="voice"):
            await pipeline.run(request)
    """
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed_ms = (time.monotonic() - start) * 1000
        try:
            histogram.record(elapsed_ms, attrs)
        except Exception:  # noqa: BLE001
            pass


def add_user_message_event(span: Any, content: str, max_length: int = 1000) -> None:
    """Record a gen_ai.user.message event for AI Toolkit Input/Output columns.

    Allows the AI Toolkit to populate the "Input" column in the trace viewer.
    Uses the OTel Events API (logs signal) to ensure events reach the AI Toolkit.

    Args:
        span: OTel span object (kept for backward compatibility; not strictly required).
        content: User message text to record.
        max_length: Maximum characters to record (default 1000 to avoid bloating events).
    """
    try:
        from opentelemetry._events import Event, get_event_logger

        truncated = content[:max_length] if content else ""
        get_event_logger("monocle").emit(
            Event(name="gen_ai.user.message", body={"content": truncated})
        )
    except Exception:  # noqa: BLE001
        pass


def add_assistant_message_event(span: Any, content: str, max_length: int = 1000) -> None:
    """Record a gen_ai.assistant.message event for AI Toolkit Input/Output columns.

    Allows the AI Toolkit to populate the "Output" column in the trace viewer.
    Uses the OTel Events API (logs signal) to ensure events reach the AI Toolkit.

    Args:
        span: OTel span object (kept for backward compatibility; not strictly required).
        content: Assistant message text to record.
        max_length: Maximum characters to record (default 1000 to avoid bloating events).
    """
    try:
        from opentelemetry._events import Event, get_event_logger

        truncated = content[:max_length] if content else ""
        get_event_logger("monocle").emit(
            Event(name="gen_ai.assistant.message", body={"content": truncated})
        )
    except Exception:  # noqa: BLE001
        pass


#endregion

# ---------------------------------------------------------------------------
#region #*   No-op stubs (used when OTel SDK is unavailable)
# ---------------------------------------------------------------------------


class _NoOpSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        pass


class _NoOpTracer:
    def start_as_current_span(self, name: str):
        from contextlib import contextmanager

        @contextmanager
        def _noop():
            yield _NoOpSpan()

        return _noop()


class _NoOpMeter:
    def create_histogram(self, *args: Any, **kwargs: Any):
        return _NoOpHistogram()

    def create_counter(self, *args: Any, **kwargs: Any):
        return _NoOpCounter()


class _NoOpHistogram:
    def record(self, amount: float, attributes: dict | None = None) -> None:
        pass


class _NoOpCounter:
    def add(self, amount: float, attributes: dict | None = None) -> None:
        pass
