"""
AmadeusProvider — intentionally a stub for live calls.

Why a stub: Amadeus is retiring its public Self-Service portal mid-2026, so a
portfolio project shouldn't depend on live keys. What's real and valuable here
is the *domain modelling*: the schemas + mapper that turn an Amadeus payload
into the same `Offer` the rest of the app already understands. `map_payload`
below is fully functional and unit-tested against a recorded fixture — it proves
the provider abstraction holds for a second, very different GDS shape.
"""

from flydesk.domain import BookingPassenger, Offer, Order, SearchCriteria
from flydesk.domain.enums import Provider
from flydesk.providers.amadeus import mapper, schemas
from flydesk.providers.base import FlightProvider

_LIVE_DISABLED = (
    "AmadeusProvider is modelled, not wired to the live API "
    "(Self-Service portal retires mid-2026). Use DuffelProvider for live calls, "
    "or AmadeusProvider.map_payload(...) to normalize a recorded payload."
)


class AmadeusProvider(FlightProvider):
    name = Provider.AMADEUS

    def search(self, criteria: SearchCriteria) -> list[Offer]:
        raise NotImplementedError(_LIVE_DISABLED)

    def get_offer(self, offer_id: str) -> Offer:
        raise NotImplementedError(_LIVE_DISABLED)

    def create_order(self, offer_id: str, passengers: list[BookingPassenger]) -> Order:
        raise NotImplementedError(_LIVE_DISABLED)

    @staticmethod
    def map_payload(raw: dict) -> list[Offer]:
        """Normalize a raw Flight Offers Search response into domain offers."""
        response = schemas.AmadeusFlightOffersResponse.model_validate(raw)
        return mapper.map_offers(response)
