"""Correlation-ID + request-metrics middleware (Phase 4 observability)."""

import time
import uuid

from flydesk.common import metrics
from flydesk.common.logging import correlation_id

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware:
    """One id per request: read or mint it, expose on the request, put it in the
    logging ContextVar, and echo it back. Foundation for cross-service tracing
    (Phase 3 also propagates it onto Kafka headers)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cid = request.headers.get(CORRELATION_HEADER) or uuid.uuid4().hex
        request.correlation_id = cid
        token = correlation_id.set(cid)
        try:
            response = self.get_response(request)
        finally:
            correlation_id.reset(token)
        response[CORRELATION_HEADER] = cid
        return response


class MetricsMiddleware:
    """Record latency + count per (method, view, status) for Prometheus."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        elapsed = time.perf_counter() - start
        view = (
            request.resolver_match.view_name
            if getattr(request, "resolver_match", None)
            else request.path
        )
        metrics.HTTP_LATENCY.labels(request.method, view).observe(elapsed)
        metrics.HTTP_REQUESTS.labels(request.method, view, str(response.status_code)).inc()
        return response
