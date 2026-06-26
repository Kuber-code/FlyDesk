"""Duffel raw payload -> domain. The anti-corruption layer, unit-tested."""

from datetime import timedelta

from flydesk.domain import BookingPassenger
from flydesk.domain.enums import CabinClass, OrderStatus, Provider
from flydesk.providers.duffel import mapper, schemas


def _offers(load):
    parsed = schemas.DuffelOfferRequestResponse.model_validate(
        load("duffel", "offer_request_response.json")
    )
    return {o.id: mapper.map_offer(o) for o in parsed.data.offers}


def test_direct_offer_is_normalized(load):
    offers = _offers(load)
    direct = offers["off_0000DirectBA01"]

    assert direct.provider is Provider.DUFFEL
    assert direct.owner.iata_code == "BA"
    assert direct.owner.name == "British Airways"
    assert direct.total.model_dump(mode="json") == {"amount": "412.40", "currency": "GBP"}
    assert direct.total_stops == 0
    assert direct.cabin_class is CabinClass.ECONOMY

    segment = direct.slices[0].segments[0]
    assert segment.flight_number == "BA175"
    assert segment.aircraft == "Boeing 777-300ER"
    assert segment.duration == timedelta(hours=8, minutes=10)


def test_connection_offer_reports_one_stop(load):
    offers = _offers(load)
    connection = offers["off_0000ConnectionEI01"]

    assert connection.total_stops == 1
    assert [s.flight_number for s in connection.slices[0].segments] == ["EI151", "EI105"]


def test_offers_sorted_cheapest_first_via_provider_semantics(load):
    # The connection (389.90) is cheaper than the direct BA (412.40).
    offers = _offers(load)
    assert offers["off_0000ConnectionEI01"].total.amount < offers["off_0000DirectBA01"].total.amount


def test_map_order_extracts_pnr(load, adult_passenger_payload):
    data = schemas.DuffelOrderResponse.model_validate(
        load("duffel", "order_create_response.json")
    ).data
    order = mapper.map_order(data, [BookingPassenger(**adult_passenger_payload)])

    assert order.provider_order_id == "ord_0000AkOrderExample01"
    assert order.booking_reference == "RZ2PML"
    assert order.status is OrderStatus.CONFIRMED
    assert order.total.amount.__str__() == "412.40"
    assert order.events and order.events[0].type == "order.created"
