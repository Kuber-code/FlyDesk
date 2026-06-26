"""DuffelProvider against mocked HTTP (respx) replaying the real captured fixtures.

How you test code that calls an external API without hitting it (interview Q36):
mock at the transport boundary, replay realistic payloads.
"""

from datetime import date

import respx
from httpx import Response

from flydesk.domain import BookingPassenger, SearchCriteria
from flydesk.providers.duffel.client import DuffelProvider

# Real ids from the captured fixtures.
OFFER_ID = "off_0000B7jtesXV1dOyGCX6by"  # cheapest AA direct
PASSENGER_SLOT = "pas_0000B7jtesIdzENdhHQFF2"


def _provider() -> DuffelProvider:
    return DuffelProvider(token="duffel_test_x", base_url="https://api.duffel.com")


@respx.mock
def test_search_returns_offers_cheapest_first(load):
    respx.route(method="POST", path="/air/offer_requests").mock(
        return_value=Response(200, json=load("duffel", "offer_request_response.json"))
    )
    offers = _provider().search(
        SearchCriteria(origin="LHR", destination="JFK", departure_date=date(2026, 8, 15))
    )
    amounts = [o.total.amount for o in offers]
    assert amounts == sorted(amounts)  # provider sorts cheapest first
    assert len(offers) == 3


@respx.mock
def test_get_offer_reprices(load):
    respx.route(method="GET", path=f"/air/offers/{OFFER_ID}").mock(
        return_value=Response(200, json=load("duffel", "offer_get_response.json"))
    )
    offer = _provider().get_offer(OFFER_ID)
    assert offer.id == OFFER_ID
    assert str(offer.total.amount) == "217.02"
    assert offer.total.currency == "USD"


@respx.mock
def test_create_order_books_real_pnr(load, adult_passenger_payload):
    respx.route(method="GET", path=f"/air/offers/{OFFER_ID}").mock(
        return_value=Response(200, json=load("duffel", "offer_get_response.json"))
    )
    create = respx.route(method="POST", path="/air/orders").mock(
        return_value=Response(201, json=load("duffel", "order_create_response.json"))
    )

    order = _provider().create_order(OFFER_ID, [BookingPassenger(**adult_passenger_payload)])

    assert order.booking_reference == "345FKK"
    assert create.called
    # we re-priced and paid the exact amount, bound to the offer's passenger slot + gender
    sent = create.calls.last.request.content
    assert PASSENGER_SLOT.encode() in sent
    assert b"217.02" in sent
    assert b'"gender"' in sent


@respx.mock
def test_provider_timeout_is_translated():
    import httpx
    import pytest

    from flydesk.common.exceptions import ProviderTimeoutError

    respx.route(method="POST", path="/air/offer_requests").mock(
        side_effect=httpx.TimeoutException("boom")
    )
    with pytest.raises(ProviderTimeoutError):
        _provider().search(
            SearchCriteria(origin="LHR", destination="JFK", departure_date=date(2026, 8, 15))
        )
