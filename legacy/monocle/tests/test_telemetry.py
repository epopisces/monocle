"""Tests for telemetry module, including route filter span processor."""
from unittest.mock import MagicMock

import pytest

from monocle.telemetry import _RouteFilterSpanProcessor

# Alias kept for brevity — tests below verify the public behaviour
_HealthCheckFilterSpanProcessor = _RouteFilterSpanProcessor


class TestHealthCheckFilterSpanProcessor:
    """Tests for the route-filter span processor (backwards-compat name)."""

    def test_filters_out_health_check_spans(self):
        """Health check spans should not be forwarded to the wrapped processor."""
        wrapped = MagicMock()
        filter_processor = _HealthCheckFilterSpanProcessor(wrapped, initial_filters=["/api/health"])

        # Create a mock span with http.route = /api/health
        health_span = MagicMock()
        health_span.attributes = {"http.route": "/api/health"}

        filter_processor.on_end(health_span)

        # on_end should NOT be called on wrapped processor for health spans
        wrapped.on_end.assert_not_called()

    def test_passes_through_non_health_spans(self):
        """Non-health-check spans should be forwarded to the wrapped processor."""
        wrapped = MagicMock()
        filter_processor = _HealthCheckFilterSpanProcessor(wrapped, initial_filters=["/api/health"])

        # Create a mock span with a different route
        app_span = MagicMock()
        app_span.attributes = {"http.route": "/api/search"}

        filter_processor.on_end(app_span)

        # on_end should be called for non-health spans
        wrapped.on_end.assert_called_once_with(app_span)

    def test_passes_through_spans_without_http_route_attribute(self):
        """Spans without http.route attribute should be passed through."""
        wrapped = MagicMock()
        filter_processor = _HealthCheckFilterSpanProcessor(wrapped, initial_filters=["/api/health"])

        # Create a mock span without http.route
        span = MagicMock()
        span.attributes = {}

        filter_processor.on_end(span)

        # on_end should be called for spans without http.route
        wrapped.on_end.assert_called_once_with(span)

    def test_on_start_always_delegates(self):
        """on_start should always delegate to the wrapped processor."""
        wrapped = MagicMock()
        filter_processor = _HealthCheckFilterSpanProcessor(wrapped, initial_filters=[])

        span = MagicMock()
        parent_context = MagicMock()

        filter_processor.on_start(span, parent_context)

        wrapped.on_start.assert_called_once_with(span, parent_context)

    def test_force_flush_delegates(self):
        """force_flush should delegate to the wrapped processor."""
        wrapped = MagicMock()
        wrapped.force_flush.return_value = True
        filter_processor = _HealthCheckFilterSpanProcessor(wrapped, initial_filters=[])

        result = filter_processor.force_flush(timeout_millis=5000)

        assert result is True
        wrapped.force_flush.assert_called_once_with(5000)

    def test_shutdown_delegates(self):
        """shutdown should delegate to the wrapped processor."""
        wrapped = MagicMock()
        filter_processor = _HealthCheckFilterSpanProcessor(wrapped, initial_filters=[])

        filter_processor.shutdown()

        wrapped.shutdown.assert_called_once()

    def test_on_ending_delegates_when_present(self):
        """_on_ending should delegate to wrapped processor if it exists."""
        wrapped = MagicMock()
        wrapped._on_ending = MagicMock()
        filter_processor = _HealthCheckFilterSpanProcessor(wrapped, initial_filters=[])

        span = MagicMock()
        filter_processor._on_ending(span)

        wrapped._on_ending.assert_called_once_with(span)

    def test_on_ending_no_op_when_not_present(self):
        """_on_ending should be a no-op if wrapped processor doesn't have it."""
        wrapped = MagicMock(spec=[])  # No _on_ending attribute
        filter_processor = _HealthCheckFilterSpanProcessor(wrapped, initial_filters=[])

        span = MagicMock()
        # Should not raise an error
        filter_processor._on_ending(span)

    def test_filters_out_health_models_spans(self):
        """/api/health/models spans should also be filtered out."""
        wrapped = MagicMock()
        filter_processor = _HealthCheckFilterSpanProcessor(wrapped, initial_filters=["/api/health"])

        health_models_span = MagicMock()
        health_models_span.attributes = {"http.route": "/api/health/models"}

        filter_processor.on_end(health_models_span)

        wrapped.on_end.assert_not_called()

    def test_set_filters_updates_filter_list(self):
        """set_filters() replaces the active filter list at runtime."""
        wrapped = MagicMock()
        filter_processor = _RouteFilterSpanProcessor(wrapped, initial_filters=["/api/health"])

        # Verify /api/capture-workbench is NOT filtered initially
        workbench_span = MagicMock()
        workbench_span.attributes = {"http.route": "/api/capture-workbench"}
        filter_processor.on_end(workbench_span)
        wrapped.on_end.assert_called_once_with(workbench_span)
        wrapped.reset_mock()

        # Update filters to suppress /api/capture-workbench as well
        filter_processor.set_filters(["/api/health", "/api/capture-workbench"])

        filter_processor.on_end(workbench_span)
        wrapped.on_end.assert_not_called()

    def test_set_filters_can_remove_all_filters(self):
        """set_filters([]) disables all filtering — everything passes through."""
        wrapped = MagicMock()
        filter_processor = _RouteFilterSpanProcessor(wrapped, initial_filters=["/api/health"])

        filter_processor.set_filters([])

        health_span = MagicMock()
        health_span.attributes = {"http.route": "/api/health"}
        filter_processor.on_end(health_span)

        wrapped.on_end.assert_called_once_with(health_span)

    def test_multiple_filters_all_applied(self):
        """All configured prefixes are checked, not just the first."""
        wrapped = MagicMock()
        filter_processor = _RouteFilterSpanProcessor(
            wrapped,
            initial_filters=["/api/health", "/api/capture-workbench", "/api/search/omni"],
        )

        for route in ["/api/health", "/api/capture-workbench", "/api/search/omni"]:
            span = MagicMock()
            span.attributes = {"http.route": route}
            filter_processor.on_end(span)

        wrapped.on_end.assert_not_called()
