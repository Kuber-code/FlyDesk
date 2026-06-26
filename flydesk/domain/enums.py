"""Domain enums. StrEnum (3.11+) so values serialize as plain strings in JSON."""

from enum import StrEnum


class Provider(StrEnum):
    DUFFEL = "duffel"
    AMADEUS = "amadeus"


class CabinClass(StrEnum):
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


class PassengerType(StrEnum):
    ADULT = "adult"
    CHILD = "child"
    INFANT_WITHOUT_SEAT = "infant_without_seat"


class PlaceType(StrEnum):
    AIRPORT = "airport"
    CITY = "city"


class OrderStatus(StrEnum):
    """Lifecycle of a booking. Phase 1 only reaches CONFIRMED; Phase 3's
    Kafka/saga flow advances CONFIRMED -> TICKETED (or FAILED + compensation)."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    TICKETED = "ticketed"
    FAILED = "failed"
    CANCELLED = "cancelled"
