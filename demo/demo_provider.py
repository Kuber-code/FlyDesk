"""
DemoProvider — an offline, bookable provider used ONLY by the interview demo.

It implements the real `FlightProvider` port (flydesk/providers/base.py) so the
demo can reuse the genuine booking use-case `create_booking` unchanged — meaning
the demo exercises the real idempotency + transactional-outbox path, not a fake.

`create_order` doesn't call any network: it looks up the offer the demo seeded
into Redis (see seed.py) and builds a domain `Order` from it. That's the whole
trick that lets a fully offline demo still flow through the production code.
"""

from __future__ import annotations

import json
import random
import string
import uuid

from flydesk.common import redis_client
from flydesk.common.exceptions import OfferNotFoundError
from flydesk.domain import BookingPassenger, Offer, Order, OrderEvent, SearchCriteria
from flydesk.domain.enums import OrderStatus, Provider
from flydesk.providers.base import FlightProvider

OFFER_KEY = "demo:offer:{offer_id}"  # per-offer lookup written by the seeder


def _pnr() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


class DemoProvider(FlightProvider):
    """Bookable, offline. Reads seeded offers from Redis; issues a fake PNR."""

    name = Provider.DUFFEL  # offers were normalized as duffel-shaped

    def search(self, criteria: SearchCriteria) -> list[Offer]:  # pragma: no cover
        raise NotImplementedError("demo search is done by seed.py, not the provider")

    def get_offer(self, offer_id: str) -> Offer:
        raw = redis_client.get_redis().get(OFFER_KEY.format(offer_id=offer_id))
        if raw is None:
            raise OfferNotFoundError(f"offer {offer_id} not in demo cache (expired?)")
        return Offer.model_validate(json.loads(raw))

    def create_order(self, offer_id: str, passengers: list[BookingPassenger]) -> Order:
        offer = self.get_offer(offer_id)
        order_id = f"ord_demo_{uuid.uuid4().hex[:12]}"
        pnr = _pnr()
        return Order(
            id=order_id,
            provider=offer.provider,
            provider_order_id=order_id,
            booking_reference=pnr,
            status=OrderStatus.CONFIRMED,
            total=offer.total,
            slices=offer.slices,
            passengers=passengers,
            events=[
                OrderEvent(
                    type="order.created",
                    detail=f"demo order {order_id} (PNR {pnr}) from offer {offer_id}",
                )
            ],
        )
