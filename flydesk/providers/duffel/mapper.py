"""
Duffel raw payload -> normalized domain model.

Pure functions, no I/O — trivially unit-testable against recorded fixtures
(see tests/fixtures/duffel/). This is where Duffel's vocabulary stops and the
domain's begins.
"""

from datetime import date

from flydesk.domain import (
    BookingPassenger,
    Carrier,
    Money,
    Offer,
    Order,
    OrderEvent,
    Place,
    Segment,
    Slice,
)
from flydesk.domain.enums import (
    CabinClass,
    OrderStatus,
    PassengerType,
    PlaceType,
    Provider,
)
from flydesk.providers.duffel import schemas


def _cabin(value: str | None) -> CabinClass | None:
    try:
        return CabinClass(value) if value else None
    except ValueError:
        return None


def _passenger_type(value: str | None) -> PassengerType:
    try:
        return PassengerType(value) if value else PassengerType.ADULT
    except ValueError:
        return PassengerType.ADULT


def _place_type(value: str | None) -> PlaceType:
    try:
        return PlaceType(value) if value else PlaceType.AIRPORT
    except ValueError:
        return PlaceType.AIRPORT


def _place(p: schemas.DuffelPlace) -> Place:
    return Place(
        iata_code=p.iata_code,
        name=p.name,
        city_name=p.city_name,
        type=_place_type(p.type),
    )


def _carrier(c: schemas.DuffelCarrier) -> Carrier:
    return Carrier(iata_code=c.iata_code, name=c.name)


def _segment(s: schemas.DuffelSegment) -> Segment:
    cabin = _cabin(s.passengers[0].cabin_class) if s.passengers else None
    return Segment(
        id=s.id,
        origin=_place(s.origin),
        destination=_place(s.destination),
        departing_at=s.departing_at,
        arriving_at=s.arriving_at,
        marketing_carrier=_carrier(s.marketing_carrier),
        operating_carrier=_carrier(s.operating_carrier) if s.operating_carrier else None,
        flight_number=f"{s.marketing_carrier.iata_code}{s.marketing_carrier_flight_number}",
        aircraft=s.aircraft.name if s.aircraft else None,
        cabin_class=cabin,
        duration=s.duration,
    )


def _slice(sl: schemas.DuffelSlice) -> Slice:
    return Slice(
        id=sl.id,
        origin=_place(sl.origin),
        destination=_place(sl.destination),
        duration=sl.duration,
        segments=[_segment(s) for s in sl.segments],
    )


def map_offer(o: schemas.DuffelOffer) -> Offer:
    first_segment = o.slices[0].segments[0] if o.slices and o.slices[0].segments else None
    cabin = (
        _cabin(first_segment.passengers[0].cabin_class)
        if first_segment and first_segment.passengers
        else None
    )
    return Offer(
        id=o.id,
        provider=Provider.DUFFEL,
        owner=_carrier(o.owner),
        total=Money(amount=o.total_amount, currency=o.total_currency),
        slices=[_slice(s) for s in o.slices],
        passenger_types=[_passenger_type(p.type) for p in o.passengers],
        cabin_class=cabin,
        expires_at=o.expires_at,
    )


def map_order(data: schemas.DuffelOrderData, passengers: list[BookingPassenger]) -> Order:
    """Map a created Duffel order to a domain Order. `passengers` is our own copy
    of the booked PII (we keep it; we don't re-read it from the provider)."""
    return Order(
        id=data.id,  # Duffel "ord_..." is unique and stable; use it as our id too
        provider=Provider.DUFFEL,
        provider_order_id=data.id,
        booking_reference=data.booking_reference,
        status=OrderStatus.CONFIRMED,
        total=Money(amount=data.total_amount, currency=data.total_currency),
        slices=[_slice(s) for s in data.slices],
        passengers=passengers,
        events=[
            OrderEvent(
                type="order.created",
                detail=f"Duffel order {data.id} (PNR {data.booking_reference})",
            )
        ],
    )


def build_offer_request_payload(
    *,
    origin: str,
    destination: str,
    departure_date: date,
    return_date: date | None,
    cabin_class: str,
    passengers: list[dict],
    max_connections: int,
) -> dict:
    """Build the POST /air/offer_requests body from search criteria."""
    slices = [
        {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date.isoformat(),
        }
    ]
    if return_date is not None:
        slices.append(
            {
                "origin": destination,
                "destination": origin,
                "departure_date": return_date.isoformat(),
            }
        )
    return {
        "data": {
            "slices": slices,
            "passengers": passengers,
            "cabin_class": cabin_class,
            "max_connections": max_connections,
        }
    }
