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


def configure_telemetry(settings: "Settings") -> None:
    """Wire up TracerProvider, MeterProvider, and root-logger handler.

    No-ops gracefully if telemetry.enabled is False.
    """
    global _tracer, _meter, _configured

    if not settings.telemetry.enabled:
        logger.info("Telemetry disabled — using no-op tracer/meter")
        _configured = True
        return

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
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
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

        # --- Auto-instrumentations ---
        LoggingInstrumentor().instrument(set_logging_format=True)
        HTTPXClientInstrumentor().instrument()
        # FastAPI instrumentation is applied in main.py after app creation

        _tracer = trace.get_tracer("monocle")
        _meter = metrics.get_meter("monocle")
        _configured = True

        logging.getLogger().setLevel(getattr(logging, settings.telemetry.log_level))
        logger.info(
            "Telemetry configured — OTLP endpoint=%s transport=%s",
            settings.telemetry.otlp_endpoint,
            settings.telemetry.otlp_transport,
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning("Telemetry setup failed (continuing without OTel): %s", exc)
        _configured = True


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
    """
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("monocle")
        with tracer.start_as_current_span(name) as s:
            for k, v in attrs.items():
                s.set_attribute(k, str(v))
            yield s
    except Exception:  # noqa: BLE001
        yield None


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


# ---------------------------------------------------------------------------
# No-op stubs (used when OTel SDK is unavailable)
# ---------------------------------------------------------------------------


class _NoOpSpan:
    def set_attribute(self, key: str, value: Any) -> None:
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
