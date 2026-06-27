"""POST /api/v1/search end-to-end through DRF, fanning out over (mocked) providers."""

from rest_framework.test import APIClient

from flydesk.providers.duffel import mapper, schemas
from flydesk.providers.mock import MockProvider
from flydesk.search import views


def _offers_from_fixture(load):
    parsed = schemas.DuffelOfferRequestResponse.model_validate(
        load("duffel", "offer_request_response.json")
    )
    return sorted((mapper.map_offer(o) for o in parsed.data.offers), key=lambda o: o.total.amount)


def test_search_returns_normalized_offers(load, monkeypatch):
    offers = _offers_from_fixture(load)
    monkeypatch.setattr(views, "get_async_providers", lambda: [MockProvider("duffel", offers)])

    client = APIClient()
    resp = client.post(
        "/api/v1/search",
        {"origin": "LHR", "destination": "JFK", "departure_date": "2026-08-15"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    assert body["degraded_providers"] == []
    assert body["offers"][0]["total"]["amount"] == "217.02"  # cheapest first (real AA fare)
    assert body["offers"][0]["provider"] == "duffel"


def test_bad_iata_is_rejected_by_serializer():
    client = APIClient()
    resp = client.post(
        "/api/v1/search",
        {"origin": "LO", "destination": "JFK", "departure_date": "2026-08-15"},
        format="json",
    )
    assert resp.status_code == 400


def test_same_origin_destination_rejected_by_domain():
    # Passes the serializer (3 chars) but fails the SearchCriteria invariant -> 400.
    client = APIClient()
    resp = client.post(
        "/api/v1/search",
        {"origin": "LHR", "destination": "LHR", "departure_date": "2026-08-15"},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"
