"""Phase 4: metrics endpoint, correlation-id JSON logs, Sentry PII scrubbing."""

import json
import logging

from rest_framework.test import APIClient

from flydesk.common import metrics
from flydesk.common.logging import CorrelationIdFilter, JsonFormatter, correlation_id
from flydesk.common.observability import scrub_pii
from flydesk.providers.duffel import mapper, schemas
from flydesk.providers.mock import MockProvider
from flydesk.search import cache


def test_metrics_endpoint_exposes_prometheus():
    resp = APIClient().get("/metrics")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "flydesk_http_requests_total" in body
    assert "flydesk_bookings_total" in body
    assert "flydesk_http_request_duration_seconds" in body


def test_search_increments_counter(load, monkeypatch):
    parsed = schemas.DuffelOfferRequestResponse.model_validate(
        load("duffel", "offer_request_response.json")
    )
    offers = [mapper.map_offer(o) for o in parsed.data.offers]
    monkeypatch.setattr(cache, "get_async_providers", lambda: [MockProvider("duffel", offers)])

    before = metrics.SEARCHES.labels(cached="false")._value.get()
    resp = APIClient().post(
        "/api/v1/search",
        {"origin": "LHR", "destination": "JFK", "departure_date": "2026-08-15"},
        format="json",
    )
    assert resp.status_code == 200
    assert metrics.SEARCHES.labels(cached="false")._value.get() == before + 1


def test_json_formatter_includes_correlation_id():
    token = correlation_id.set("abc123")
    try:
        record = logging.LogRecord(
            "flydesk", logging.INFO, __file__, 1, "hello %s", ("world",), None
        )
        CorrelationIdFilter().filter(record)
        out = json.loads(JsonFormatter().format(record))
    finally:
        correlation_id.reset(token)

    assert out["message"] == "hello world"
    assert out["correlation_id"] == "abc123"
    assert out["level"] == "INFO"
    assert out["logger"] == "flydesk"


def test_correlation_id_header_is_echoed():
    resp = APIClient().get("/healthz", HTTP_X_CORRELATION_ID="trace-xyz")
    assert resp["X-Correlation-ID"] == "trace-xyz"


def test_scrub_pii_redacts_sensitive_keys():
    event = {
        "level": "error",
        "extra": {
            "passengers": [{"given_name": "Tony", "family_name": "Stark"}],
            "email": "tony@example.com",
            "order_id": "ord_123",
        },
    }
    scrubbed = scrub_pii(event)

    assert scrubbed["extra"]["passengers"] == "[scrubbed]"
    assert scrubbed["extra"]["email"] == "[scrubbed]"
    assert scrubbed["extra"]["order_id"] == "ord_123"  # non-PII preserved
    assert scrubbed["level"] == "error"
