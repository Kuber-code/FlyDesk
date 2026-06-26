"""Correlation-ID middleware: one ID per request, echoed back and logged.

Foundation for cross-service tracing (Phase 3 propagates it onto Kafka headers,
Phase 4 puts it in structured JSON logs and Sentry tags).
"""

import uuid

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = request.headers.get(CORRELATION_HEADER) or uuid.uuid4().hex
        request.correlation_id = correlation_id
        response = self.get_response(request)
        response[CORRELATION_HEADER] = correlation_id
        return response
