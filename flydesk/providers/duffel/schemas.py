"""
Pydantic models of Duffel's *raw* payloads — the anti-corruption boundary.

`extra="ignore"` is deliberate: Duffel returns dozens of fields we don't use;
we parse only what we map, and unknown/new fields can't break us. Anything that
IS malformed in a field we rely on fails fast here, at the edge (interview Q26),
instead of leaking `None`s deep into the app.

Reference: Duffel Flights API — Offer Requests, Offers, Orders.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class _Raw(BaseModel):
    model_config = ConfigDict(extra="ignore")


class DuffelPlace(_Raw):
    iata_code: str | None = None
    name: str | None = None
    city_name: str | None = None
    type: str | None = None  # "airport" | "city"


class DuffelCarrier(_Raw):
    iata_code: str
    name: str | None = None


class DuffelAircraft(_Raw):
    iata_code: str | None = None
    name: str | None = None


class DuffelSegmentPassenger(_Raw):
    passenger_id: str | None = None
    cabin_class: str | None = None
    cabin_class_marketing_name: str | None = None
    fare_basis_code: str | None = None


class DuffelSegment(_Raw):
    id: str
    origin: DuffelPlace
    destination: DuffelPlace
    departing_at: datetime
    arriving_at: datetime
    marketing_carrier: DuffelCarrier
    operating_carrier: DuffelCarrier | None = None
    marketing_carrier_flight_number: str
    aircraft: DuffelAircraft | None = None
    duration: str | None = None  # ISO-8601 e.g. "PT7H50M"
    passengers: list[DuffelSegmentPassenger] = Field(default_factory=list)


class DuffelSlice(_Raw):
    id: str
    origin: DuffelPlace
    destination: DuffelPlace
    duration: str | None = None
    segments: list[DuffelSegment]


class DuffelOfferPassenger(_Raw):
    id: str
    type: str | None = None  # "adult" | "child" | "infant_without_seat"


class DuffelOffer(_Raw):
    id: str
    owner: DuffelCarrier
    total_amount: Decimal
    total_currency: str
    base_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    slices: list[DuffelSlice]
    passengers: list[DuffelOfferPassenger] = Field(default_factory=list)
    expires_at: datetime | None = None


class DuffelOfferRequestData(_Raw):
    id: str
    offers: list[DuffelOffer] = Field(default_factory=list)


class DuffelOfferRequestResponse(_Raw):
    """Response of POST /air/offer_requests?return_offers=true."""

    data: DuffelOfferRequestData


class DuffelOfferResponse(_Raw):
    """Response of GET /air/offers/{id}."""

    data: DuffelOffer


class DuffelOrderData(_Raw):
    id: str
    booking_reference: str | None = None  # the PNR
    total_amount: Decimal
    total_currency: str
    slices: list[DuffelSlice]


class DuffelOrderResponse(_Raw):
    """Response of POST /air/orders."""

    data: DuffelOrderData
