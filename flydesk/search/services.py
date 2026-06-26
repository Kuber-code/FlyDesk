"""Search use-case: validated request dict -> normalized offers (as JSON dicts).

Keeping this out of the view (interview Q9) makes it reusable (CLI, tests, a
future async endpoint) and keeps the view purely about HTTP.
"""

import logging

from flydesk.domain import PassengerSpec, SearchCriteria
from flydesk.providers import get_provider

logger = logging.getLogger("flydesk.search")


def search_offers(data: dict, *, provider_name: str | None = None) -> list[dict]:
    passengers = [PassengerSpec(**p) for p in (data.get("passengers") or [{}])]
    # SearchCriteria applies the domain invariants and raises on violation;
    # the DRF exception handler turns that into a 400.
    criteria = SearchCriteria(
        origin=data["origin"],
        destination=data["destination"],
        departure_date=data["departure_date"],
        return_date=data.get("return_date"),
        cabin_class=data.get("cabin_class", "economy"),
        passengers=passengers,
        max_connections=data.get("max_connections", 1),
    )
    provider = get_provider(provider_name)
    offers = provider.search(criteria)
    logger.info("search route=%s-%s offers=%d", criteria.origin, criteria.destination, len(offers))
    return [o.model_dump(mode="json") for o in offers]
