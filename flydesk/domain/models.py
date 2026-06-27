"""
Normalized domain models (Pydantic v2).

These are the shapes the rest of the system speaks. Every provider's raw payload
is mapped *into* these models in its own mapper (the anti-corruption layer), so
nothing provider-specific leaks past `flydesk/providers/`.

Pydantic features on display here (interview Q25/Q26):
- field & model validators (IATA codes, round-trip date ordering),
- typed coercion (ISO-8601 duration string -> timedelta, Decimal money),
- computed fields (stop counts, expiry),
- custom serializers (money as string, never float).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from flydesk.domain.enums import (
    CabinClass,
    OrderStatus,
    PassengerType,
    PlaceType,
    Provider,
)

# --------------------------------------------------------------------------- #
# Reusable validated value types
# --------------------------------------------------------------------------- #


def _airport_code(value: str) -> str:
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError(f"airport IATA code must be 3 letters, got {value!r}")
    return code


def _carrier_code(value: str) -> str:
    # Airline IATA codes are 2 alphanumeric chars (e.g. BA, U2, W6).
    code = value.strip().upper()
    if len(code) != 2 or not code.isalnum():
        raise ValueError(f"airline IATA code must be 2 alphanumeric chars, got {value!r}")
    return code


AirportCode = Annotated[str, AfterValidator(_airport_code)]
CarrierCode = Annotated[str, AfterValidator(_carrier_code)]


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #


class Money(BaseModel):
    """Money is Decimal + ISO-4217 currency. Never a float — and serialized as a
    string so JSON consumers can't silently lose precision."""

    model_config = ConfigDict(extra="forbid")

    amount: Decimal
    currency: str

    @field_validator("currency")
    @classmethod
    def _currency_iso4217(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO-4217 code")
        return v

    @field_serializer("amount")
    def _amount_as_str(self, v: Decimal) -> str:
        return f"{v:.2f}"


class Place(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iata_code: AirportCode
    name: str | None = None
    city_name: str | None = None
    type: PlaceType = PlaceType.AIRPORT


class Carrier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iata_code: CarrierCode
    name: str | None = None


class Segment(BaseModel):
    """A single operated leg flown without changing aircraft."""

    model_config = ConfigDict(extra="forbid")

    id: str
    origin: Place
    destination: Place
    departing_at: datetime
    arriving_at: datetime
    marketing_carrier: Carrier
    operating_carrier: Carrier | None = None
    flight_number: str
    aircraft: str | None = None
    cabin_class: CabinClass | None = None
    duration: timedelta | None = None  # ISO-8601 "PT8H30M" coerces to timedelta


class Slice(BaseModel):
    """One directional journey (e.g. the outbound), made of 1+ segments.
    More than one segment means a connection."""

    # extra="ignore" (not "forbid") because this model has a computed field
    # (`stops`) that model_dump emits; we must tolerate it on the round-trip
    # back in (Mongo persistence now, Redis offer-cache in Phase 2).
    model_config = ConfigDict(extra="ignore")

    id: str
    origin: Place
    destination: Place
    duration: timedelta | None = None
    segments: list[Segment] = Field(min_length=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stops(self) -> int:
        return len(self.segments) - 1


class Offer(BaseModel):
    """A normalized, bookable price for an itinerary. Ephemeral: it expires, and
    must be re-priced before booking (interview Q40)."""

    # extra="ignore" for the same round-trip reason as Slice (computed
    # `total_stops`; Phase 2 caches offers as JSON in Redis).
    model_config = ConfigDict(extra="ignore")

    id: str
    provider: Provider
    owner: Carrier
    total: Money
    slices: list[Slice] = Field(min_length=1)
    passenger_types: list[PassengerType] = Field(default_factory=list)
    cabin_class: CabinClass | None = None
    expires_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_stops(self) -> int:
        return sum(s.stops for s in self.slices)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or datetime.now(UTC)
        # expires_at may be naive (provider local) — compare defensively.
        if self.expires_at.tzinfo is None:
            return self.expires_at < now.replace(tzinfo=None)
        return self.expires_at < now


# --------------------------------------------------------------------------- #
# Search input
# --------------------------------------------------------------------------- #


class PassengerSpec(BaseModel):
    """Who is travelling (for the search), without PII — just a type and optional
    age for children."""

    model_config = ConfigDict(extra="forbid")

    type: PassengerType = PassengerType.ADULT
    age: int | None = Field(default=None, ge=0, le=17)


class SearchCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: AirportCode
    destination: AirportCode
    departure_date: date
    return_date: date | None = None
    cabin_class: CabinClass = CabinClass.ECONOMY
    passengers: list[PassengerSpec] = Field(default_factory=lambda: [PassengerSpec()], min_length=1)
    max_connections: int = Field(default=1, ge=0, le=2)

    @model_validator(mode="after")
    def _validate_dates_and_route(self) -> "SearchCriteria":
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        if self.return_date is not None and self.return_date < self.departure_date:
            raise ValueError("return_date must be on or after departure_date")
        return self

    @property
    def is_round_trip(self) -> bool:
        return self.return_date is not None


# --------------------------------------------------------------------------- #
# Booking input + order
# --------------------------------------------------------------------------- #


class BookingPassenger(BaseModel):
    """Full passenger details required to create an order (PII)."""

    model_config = ConfigDict(extra="forbid")

    type: PassengerType = PassengerType.ADULT
    title: str | None = None
    gender: str | None = None  # Duffel requires "m"/"f" on order passengers (live-API finding)
    given_name: str
    family_name: str
    born_on: date
    email: str
    phone_number: str
    # Optional provider-assigned passenger id to bind details to the offer's slots.
    provider_passenger_id: str | None = None


class OrderEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detail: str | None = None


class OutboxEvent(BaseModel):
    """A domain event staged for reliable publish (transactional outbox, Q30).

    Stored *inside* the order document, so it's written in the same atomic
    single-document write as the state change — the DB write and the "event
    exists" fact can't diverge. A relay later publishes it and stamps
    `published_at`."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str
    payload: dict
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None


class Order(BaseModel):
    """Persisted booking document (stored in MongoDB, read as one document)."""

    model_config = ConfigDict(extra="forbid")

    id: str  # our internal id (also the Mongo _id)
    provider: Provider
    provider_order_id: str  # e.g. Duffel "ord_..."
    booking_reference: str | None = None  # the PNR
    status: OrderStatus = OrderStatus.PENDING
    total: Money
    slices: list[Slice]
    passengers: list[BookingPassenger]
    idempotency_key: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    events: list[OrderEvent] = Field(default_factory=list)
    outbox: list[OutboxEvent] = Field(default_factory=list)
