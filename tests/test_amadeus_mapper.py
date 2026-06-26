"""Amadeus raw payload -> domain. Same target type as Duffel, different shape."""

from flydesk.domain.enums import CabinClass, PassengerType, Provider
from flydesk.providers.amadeus.provider import AmadeusProvider


def test_amadeus_search_normalizes_round_trip(load):
    offers = AmadeusProvider.map_payload(load("amadeus", "flight_offers_search_response.json"))
    assert len(offers) == 1
    offer = offers[0]

    assert offer.provider is Provider.AMADEUS
    # round trip -> two slices; outbound has a connection (2 segments), return is direct
    assert len(offer.slices) == 2
    assert offer.slices[0].stops == 1
    assert offer.slices[1].stops == 0
    assert offer.total_stops == 1


def test_dictionaries_resolve_names_and_codes(load):
    offer = AmadeusProvider.map_payload(load("amadeus", "flight_offers_search_response.json"))[0]

    # owner is the validating carrier TG, name resolved from `dictionaries.carriers`
    assert offer.owner.iata_code == "TG"
    assert offer.owner.name == "THAI AIRWAYS INTERNATIONAL"

    first_segment = offer.slices[0].segments[0]
    assert first_segment.flight_number == "QF81"
    assert first_segment.aircraft == "AIRBUS A380-800"  # resolved from dictionaries.aircraft
    assert first_segment.cabin_class is CabinClass.ECONOMY


def test_amadeus_money_and_passenger_types(load):
    offer = AmadeusProvider.map_payload(load("amadeus", "flight_offers_search_response.json"))[0]
    assert offer.total.model_dump(mode="json") == {"amount": "1054.70", "currency": "EUR"}
    assert offer.passenger_types == [PassengerType.ADULT]


def test_amadeus_price_response_flightoffers_also_parse(load):
    # The pricing response wraps the same offer shape under data.flightOffers.
    raw = load("amadeus", "flight_offers_price_response.json")
    normalized = AmadeusProvider.map_payload(
        {"data": raw["data"]["flightOffers"], "dictionaries": raw.get("dictionaries")}
    )
    # price moved between search and pricing — offers are perishable (Q40)
    assert normalized[0].total.model_dump(mode="json")["amount"] == "1078.30"
