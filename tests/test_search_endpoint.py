"""POST /api/v1/search end-to-end through DRF (provider faked)."""

from rest_framework.test import APIClient

from flydesk.providers.duffel import mapper, schemas
from flydesk.search import services


def _offers_from_fixture(load):
    parsed = schemas.DuffelOfferRequestResponse.model_validate(
        load("duffel", "offer_request_response.json")
    )
    return sorted((mapper.map_offer(o) for o in parsed.data.offers), key=lambda o: o.total.amount)


class _FakeProvider:
    def __init__(self, offers):
        self._offers = offers

    def search(self, criteria):
        return self._offers


def test_search_returns_normalized_offers(load, monkeypatch):
    monkeypatch.setattr(
        services, "get_provider", lambda name=None: _FakeProvider(_offers_from_fixture(load))
    )
    client = APIClient()
    resp = client.post(
        "/api/v1/search",
        {"origin": "LHR", "destination": "JFK", "departure_date": "2026-08-15"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["offers"][0]["total"]["amount"] == "389.90"  # cheapest first
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
