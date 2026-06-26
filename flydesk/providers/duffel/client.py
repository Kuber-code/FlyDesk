"""
DuffelProvider — the live integration (Phase 1: synchronous httpx).

Phase 2 swaps this for an async `aiohttp`/`httpx.AsyncClient` version with
semaphores, per-request timeouts, retries+backoff and a circuit breaker. Keeping
all Duffel I/O behind this class means none of that leaks into the app.
"""

import logging

import httpx

from flydesk.common.config import get_settings
from flydesk.common.exceptions import (
    OfferNotFoundError,
    ProviderError,
    ProviderTimeoutError,
)
from flydesk.domain import BookingPassenger, Offer, Order, SearchCriteria
from flydesk.domain.enums import PassengerType, Provider
from flydesk.providers.base import FlightProvider
from flydesk.providers.duffel import mapper, schemas

logger = logging.getLogger("flydesk.providers.duffel")


def _passengers_for_request(criteria: SearchCriteria) -> list[dict]:
    """Duffel expects adults as {"type": "adult"} and children by {"age": N}."""
    out: list[dict] = []
    for p in criteria.passengers:
        if p.type == PassengerType.ADULT:
            out.append({"type": "adult"})
        elif p.age is not None:
            out.append({"age": p.age})
        else:
            out.append({"type": p.type.value})
    return out


class DuffelProvider(FlightProvider):
    name = Provider.DUFFEL

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        version: str | None = None,
        timeout: float = 15.0,
        http_client: httpx.Client | None = None,
    ):
        settings = get_settings()
        self._version = version or settings.duffel_api_version
        # One reused client = connection pooling + keep-alive (interview Q4).
        self._http = http_client or httpx.Client(
            base_url=(base_url or settings.duffel_api_url).rstrip("/"),
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token or settings.duffel_api_token}",
                "Duffel-Version": self._version,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    # --- transport -------------------------------------------------------- #

    def _request(self, method: str, path: str, *, json: dict | None = None) -> dict:
        try:
            response = self._http.request(method, path, json=json)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Duffel timed out on {method} {path}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Duffel transport error: {exc}") from exc

        if response.status_code == 404:
            raise OfferNotFoundError()
        if response.status_code >= 400:
            logger.warning(
                "duffel_error status=%s body=%s", response.status_code, response.text[:300]
            )
            raise ProviderError(f"Duffel returned HTTP {response.status_code}")
        return response.json()

    # --- FlightProvider --------------------------------------------------- #

    def search(self, criteria: SearchCriteria) -> list[Offer]:
        payload = mapper.build_offer_request_payload(
            origin=criteria.origin,
            destination=criteria.destination,
            departure_date=criteria.departure_date,
            return_date=criteria.return_date,
            cabin_class=criteria.cabin_class.value,
            passengers=_passengers_for_request(criteria),
            max_connections=criteria.max_connections,
        )
        raw = self._request("POST", "/air/offer_requests?return_offers=true", json=payload)
        parsed = schemas.DuffelOfferRequestResponse.model_validate(raw)
        offers = [mapper.map_offer(o) for o in parsed.data.offers]
        offers.sort(key=lambda o: o.total.amount)  # cheapest first
        logger.info(
            "duffel_search offers=%d route=%s-%s",
            len(offers),
            criteria.origin,
            criteria.destination,
        )
        return offers

    def get_offer(self, offer_id: str) -> Offer:
        raw = self._request("GET", f"/air/offers/{offer_id}")
        parsed = schemas.DuffelOfferResponse.model_validate(raw)
        return mapper.map_offer(parsed.data)

    def create_order(self, offer_id: str, passengers: list[BookingPassenger]) -> Order:
        # Re-fetch the offer to bind passengers to its slots and to pay the exact
        # current amount (re-price before book — interview Q40).
        raw_offer = self._request("GET", f"/air/offers/{offer_id}")
        offer = schemas.DuffelOfferResponse.model_validate(raw_offer).data

        duffel_passengers = []
        for slot, person in zip(offer.passengers, passengers, strict=False):
            duffel_passengers.append(
                {
                    "id": slot.id,
                    "title": person.title or "mr",
                    "given_name": person.given_name,
                    "family_name": person.family_name,
                    "born_on": person.born_on.isoformat(),
                    "email": person.email,
                    "phone_number": person.phone_number,
                }
            )

        payload = {
            "data": {
                "type": "instant",
                "selected_offers": [offer.id],
                "payments": [
                    {
                        "type": "balance",
                        "currency": offer.total_currency,
                        "amount": str(offer.total_amount),
                    }
                ],
                "passengers": duffel_passengers,
            }
        }
        raw = self._request("POST", "/air/orders", json=payload)
        data = schemas.DuffelOrderResponse.model_validate(raw).data
        logger.info("duffel_order_created id=%s pnr=%s", data.id, data.booking_reference)
        return mapper.map_order(data, passengers)
