"""DuffelProvider against mocked HTTP (respx) using the recorded fixtures.

This is how you test code that calls an external API without hitting it
(interview Q36): mock at the transport boundary, replay realistic payloads.
"""

from datetime import date

import respx
from httpx import Response

from flydesk.domain import BookingPassenger, SearchCriteria
from flydesk.providers.duffel.client import DuffelProvider


def _provider() -> DuffelProvider:
    return DuffelProvider(token="duffel_test_x", base_url="https://api.duffel.com")


@respx.mock
def test_search_returns_sorted_offers(load):
    respx.route(method="POST", path="/air/offer_requests").mock(
        return_value=Response(200, json=load("duffel", "offer_request_response.json"))
    )
    offers = _provider().search(
        SearchCriteria(origin="LHR", destination="JFK", departure_date=date(2026, 8, 15))
    )
    assert [o.id for o in offers] == [
        "off_0000ConnectionEI01",
        "off_0000DirectBA01",
    ]  # cheapest first


@respx.mock
def test_get_offer_reprices(load):
    respx.route(method="GET", path="/air/offers/off_0000DirectBA01").mock(
        return_value=Response(200, json=load("duffel", "offer_get_response.json"))
    )
    offer = _provider().get_offer("off_0000DirectBA01")
    assert offer.id == "off_0000DirectBA01"
    assert offer.total.amount.__str__() == "412.40"


@respx.mock
def test_create_order_books_pnr(load, adult_passenger_payload):
    respx.route(method="GET", path="/air/offers/off_0000DirectBA01").mock(
        return_value=Response(200, json=load("duffel", "offer_get_response.json"))
    )
    create = respx.route(method="POST", path="/air/orders").mock(
        return_value=Response(201, json=load("duffel", "order_create_response.json"))
    )

    order = _provider().create_order(
        "off_0000DirectBA01", [BookingPassenger(**adult_passenger_payload)]
    )

    assert order.booking_reference == "RZ2PML"
    assert create.called
    # the booking payload paid the exact re-priced amount with the offer's passenger slot
    sent = create.calls.last.request
    assert b"pas_0000AkPassengerAdult01" in sent.content
    assert b"412.40" in sent.content


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
