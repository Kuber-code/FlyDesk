"""Provider-agnostic domain models (the normalized form every provider maps to)."""

from flydesk.domain.enums import (
    CabinClass,
    OrderStatus,
    PassengerType,
    PlaceType,
    Provider,
)
from flydesk.domain.models import (
    BookingPassenger,
    Carrier,
    Money,
    Offer,
    Order,
    OrderEvent,
    PassengerSpec,
    Place,
    SearchCriteria,
    Segment,
    Slice,
)

__all__ = [
    "CabinClass",
    "OrderStatus",
    "PassengerType",
    "PlaceType",
    "Provider",
    "BookingPassenger",
    "Carrier",
    "Money",
    "Offer",
    "Order",
    "OrderEvent",
    "PassengerSpec",
    "Place",
    "SearchCriteria",
    "Segment",
    "Slice",
]
