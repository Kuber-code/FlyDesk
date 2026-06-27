"""
AsyncDuffelProvider — the async search path (Phase 2).

Same anti-corruption layer (`schemas` + `mapper`) as the sync client; only the
transport changes (httpx.AsyncClient). That reuse is the payoff of putting the
ACL in pure functions.
"""

import logging

import httpx

from flydesk.common.config import get_settings
from flydesk.common.exceptions import ProviderError, ProviderTimeoutError
from flydesk.domain import Offer, SearchCriteria
from flydesk.domain.enums import Provider
from flydesk.providers.base import AsyncFlightProvider
from flydesk.providers.duffel import mapper, schemas
from flydesk.providers.duffel.client import _passengers_for_request

logger = logging.getLogger("flydesk.providers.duffel")


class AsyncDuffelProvider(AsyncFlightProvider):
    name = Provider.DUFFEL

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        version: str | None = None,
        timeout: float = 15.0,
    ):
        settings = get_settings()
        self._base_url = (base_url or settings.duffel_api_url).rstrip("/")
        self._version = version or settings.duffel_api_version
        self._token = token or settings.duffel_api_token
        self._timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Duffel-Version": self._version,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def search(self, criteria: SearchCriteria) -> list[Offer]:
        payload = mapper.build_offer_request_payload(
            origin=criteria.origin,
            destination=criteria.destination,
            departure_date=criteria.departure_date,
            return_date=criteria.return_date,
            cabin_class=criteria.cabin_class.value,
            passengers=_passengers_for_request(criteria),
            max_connections=criteria.max_connections,
        )
        try:
            # A fresh client per call keeps us safe across event loops (the sync
            # boundary uses async_to_sync). A long-lived ASGI server would reuse a
            # client bound to its loop for connection pooling (interview Q4).
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, headers=self._headers()
            ) as client:
                response = await client.post("/air/offer_requests?return_offers=true", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Duffel timed out on search") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Duffel transport error: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(f"Duffel returned HTTP {response.status_code}")

        parsed = schemas.DuffelOfferRequestResponse.model_validate(response.json())
        offers = [mapper.map_offer(o) for o in parsed.data.offers]
        offers.sort(key=lambda o: o.total.amount)
        return offers
