"""
Amadeus raw payload -> normalized domain model.

Note how this resolves names from the `dictionaries` block (carrier/aircraft
codes -> human names) — a quirk of Amadeus the domain never has to know about.
Same output type (`Offer`) as the Duffel mapper: that's the whole point.
"""

from flydesk.domain import Carrier, Money, Offer, Place, Segment, Slice
from flydesk.domain.enums import CabinClass, PassengerType, Provider
from flydesk.providers.amadeus import schemas

_TRAVELER_TYPE = {
    "ADULT": PassengerType.ADULT,
    "CHILD": PassengerType.CHILD,
    "HELD_INFANT": PassengerType.INFANT_WITHOUT_SEAT,
    "SEATED_INFANT": PassengerType.CHILD,
}


def _cabin(value: str | None) -> CabinClass | None:
    try:
        return CabinClass(value.lower()) if value else None
    except ValueError:
        return None


def _place(iata_code: str, dictionaries: schemas.AmadeusDictionaries | None) -> Place:
    city_name = None
    if dictionaries and iata_code in dictionaries.locations:
        city_name = dictionaries.locations[iata_code].get("cityCode")
    return Place(iata_code=iata_code, city_name=city_name)


def _carrier(code: str, dictionaries: schemas.AmadeusDictionaries | None) -> Carrier:
    name = dictionaries.carriers.get(code) if dictionaries else None
    return Carrier(iata_code=code, name=name)


def _segment(
    seg: schemas.AmadeusSegment,
    cabin_by_segment: dict[str, str | None],
    dictionaries: schemas.AmadeusDictionaries | None,
) -> Segment:
    aircraft_name = None
    if seg.aircraft and seg.aircraft.code and dictionaries:
        aircraft_name = dictionaries.aircraft.get(seg.aircraft.code)
    return Segment(
        id=seg.id,
        origin=_place(seg.departure.iata_code, dictionaries),
        destination=_place(seg.arrival.iata_code, dictionaries),
        departing_at=seg.departure.at,
        arriving_at=seg.arrival.at,
        marketing_carrier=_carrier(seg.carrier_code, dictionaries),
        operating_carrier=(
            _carrier(seg.operating.carrier_code, dictionaries)
            if seg.operating and seg.operating.carrier_code
            else None
        ),
        flight_number=f"{seg.carrier_code}{seg.number}",
        aircraft=aircraft_name or (seg.aircraft.code if seg.aircraft else None),
        cabin_class=_cabin(cabin_by_segment.get(seg.id)),
        duration=seg.duration,
    )


def map_offer(
    offer: schemas.AmadeusFlightOffer,
    dictionaries: schemas.AmadeusDictionaries | None = None,
) -> Offer:
    # Build segment_id -> cabin from the first traveler's fare details.
    cabin_by_segment: dict[str, str | None] = {}
    if offer.traveler_pricings:
        for fd in offer.traveler_pricings[0].fare_details_by_segment:
            cabin_by_segment[fd.segment_id] = fd.cabin

    slices: list[Slice] = []
    for idx, itin in enumerate(offer.itineraries):
        segments = [_segment(s, cabin_by_segment, dictionaries) for s in itin.segments]
        slices.append(
            Slice(
                id=f"{offer.id}-itin-{idx}",  # Amadeus itineraries have no id; synthesize one
                origin=segments[0].origin,
                destination=segments[-1].destination,
                duration=itin.duration,
                segments=segments,
            )
        )

    owner_code = (
        offer.validating_airline_codes[0]
        if offer.validating_airline_codes
        else (offer.itineraries[0].segments[0].carrier_code)
    )
    first_cabin = next(iter(cabin_by_segment.values()), None)

    return Offer(
        id=offer.id,
        provider=Provider.AMADEUS,
        owner=_carrier(owner_code, dictionaries),
        total=Money(
            amount=offer.price.grand_total or offer.price.total, currency=offer.price.currency
        ),
        slices=slices,
        passenger_types=[
            _TRAVELER_TYPE.get(tp.traveler_type, PassengerType.ADULT)
            for tp in offer.traveler_pricings
        ],
        cabin_class=_cabin(first_cabin),
        expires_at=None,  # Amadeus carries validity differently (lastTicketingDate)
    )


def map_offers(response: schemas.AmadeusFlightOffersResponse) -> list[Offer]:
    return [map_offer(o, response.dictionaries) for o in response.data]
