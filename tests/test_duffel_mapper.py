"""Duffel raw payload -> domain. The anti-corruption layer, unit-tested.

Fixtures here are REAL captures from the Duffel sandbox (see scripts/capture_duffel.py),
trimmed to a few representative offers. The mapper must survive the full, noisy
real shape — that's the whole point of the ACL.
"""

import re

from flydesk.domain import BookingPassenger
from flydesk.domain.enums import CabinClass, OrderStatus, Provider
from flydesk.providers.duffel import mapper, schemas


def _offers(load):
    parsed = schemas.DuffelOfferRequestResponse.model_validate(
        load("duffel", "offer_request_response.json")
    )
    return [mapper.map_offer(o) for o in parsed.data.offers]


def test_every_live_offer_parses_and_normalizes(load):
    offers = _offers(load)
    assert len(offers) >= 2
    assert all(o.provider is Provider.DUFFEL for o in offers)
    # carrier codes are 2 chars, money is USD on this route
    assert all(len(o.owner.iata_code) == 2 for o in offers)
    assert all(o.total.currency == "USD" for o in offers)


def test_cheapest_direct_offer_is_normalized(load):
    direct = min((o for o in _offers(load) if o.total_stops == 0), key=lambda o: o.total.amount)
    assert direct.cabin_class is CabinClass.ECONOMY
    segment = direct.slices[0].segments[0]
    # normalized flight number = carrier code + number, e.g. "AA10"
    assert re.match(r"^[A-Z0-9]{2}\d+$", segment.flight_number)
    assert segment.origin.iata_code == "LHR"
    assert segment.destination.iata_code == "JFK"


def test_connection_offer_reports_its_stops(load):
    connection = next((o for o in _offers(load) if o.total_stops >= 1), None)
    assert connection is not None, "expected at least one multi-segment offer in the capture"
    multi = max(connection.slices, key=lambda s: s.stops)
    assert multi.stops == len(multi.segments) - 1
    assert len(multi.segments) >= 2


def test_map_order_extracts_real_pnr(load, adult_passenger_payload):
    data = schemas.DuffelOrderResponse.model_validate(
        load("duffel", "order_create_response.json")
    ).data
    order = mapper.map_order(data, [BookingPassenger(**adult_passenger_payload)])

    assert order.provider_order_id.startswith("ord_")
    assert order.booking_reference == "345FKK"
    assert order.status is OrderStatus.CONFIRMED
    assert order.total.currency == "USD"
    assert order.events and order.events[0].type == "order.created"
