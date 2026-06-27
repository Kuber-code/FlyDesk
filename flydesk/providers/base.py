"""
The `FlightProvider` port and a factory.

This is the seam that makes the whole project "provider-agnostic": the rest of
the app depends only on this interface and the domain models, never on Duffel or
Amadeus directly. Duffel is wired live; Amadeus is modelled (schemas + mapper)
because its Self-Service portal is retiring mid-2026 (interview Q42).
"""

from abc import ABC, abstractmethod

from flydesk.domain import BookingPassenger, Offer, Order, SearchCriteria
from flydesk.domain.enums import Provider


class FlightProvider(ABC):
    """Port for a flight content + booking provider. Mirrors the universal
    shop -> price -> book flow (interview Q39)."""

    name: Provider

    @abstractmethod
    def search(self, criteria: SearchCriteria) -> list[Offer]:
        """Shop: return normalized offers for the criteria."""

    @abstractmethod
    def get_offer(self, offer_id: str) -> Offer:
        """Price/revalidate: fetch a single offer fresh, right before booking."""

    @abstractmethod
    def create_order(self, offer_id: str, passengers: list[BookingPassenger]) -> Order:
        """Book: create the order/PNR for an offer with passenger details."""


def get_provider(name: str | None = None) -> FlightProvider:
    """Resolve the configured provider. Defaults to FLYDESK_PROVIDER."""
    from flydesk.common.config import get_settings

    resolved = (name or get_settings().provider).lower()
    if resolved == Provider.DUFFEL:
        from flydesk.providers.duffel.client import DuffelProvider

        return DuffelProvider()
    if resolved == Provider.AMADEUS:
        from flydesk.providers.amadeus.provider import AmadeusProvider

        return AmadeusProvider()
    raise ValueError(f"unknown provider: {resolved!r}")


class AsyncFlightProvider(ABC):
    """Async port for the read-heavy **search** path (Phase 2).

    Search is I/O-bound fan-out to several providers at once — the textbook case
    for asyncio (interview Q1). Booking stays on the sync `FlightProvider` (it's a
    single, correctness-critical write, not a fan-out)."""

    name: object  # Provider enum or a free string for mocks

    @abstractmethod
    async def search(self, criteria: SearchCriteria) -> list[Offer]: ...


def get_async_providers() -> list[AsyncFlightProvider]:
    """The providers search fans out across. Today just async Duffel; drop in an
    NDC/LCC feed or a second GDS here and the fan-out picks it up automatically."""
    from flydesk.providers.duffel.async_client import AsyncDuffelProvider

    return [AsyncDuffelProvider()]
