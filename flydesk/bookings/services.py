"""
Booking use-cases.

Idempotency (interview Q31): the client sends an `Idempotency-Key`. Phase 1
dedups on read + a unique Mongo index, so a retry/double-click returns the same
order instead of double-booking. Phase 2 strengthens this by *reserving* the key
in Redis (SETNX) *before* calling the provider, closing the small window where
two concurrent requests could both reach the provider.
"""

import logging

from pymongo.errors import DuplicateKeyError

from flydesk.common.exceptions import BookingNotFoundError
from flydesk.domain import BookingPassenger, Order
from flydesk.providers import get_provider

from .repository import OrderRepository, ensure_order_indexes

logger = logging.getLogger("flydesk.bookings")


def create_booking(
    *,
    offer_id: str,
    passengers_data: list[dict],
    idempotency_key: str | None = None,
    provider_name: str | None = None,
    repository: OrderRepository | None = None,
) -> Order:
    repo = repository or OrderRepository()
    ensure_order_indexes()

    if idempotency_key:
        existing = repo.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info("idempotent_replay key=%s order=%s", idempotency_key, existing.id)
            return existing

    passengers = [BookingPassenger(**p) for p in passengers_data]
    provider = get_provider(provider_name)

    # re-price (inside the provider) -> create order/PNR
    order = provider.create_order(offer_id, passengers)
    if idempotency_key:
        order = order.model_copy(update={"idempotency_key": idempotency_key})

    try:
        repo.save(order)
    except DuplicateKeyError:
        # Lost a race on the same idempotency key — return the winner's order.
        winner = repo.find_by_idempotency_key(idempotency_key) if idempotency_key else None
        if winner is not None:
            logger.info("idempotent_race key=%s order=%s", idempotency_key, winner.id)
            return winner
        raise

    logger.info("booking_created order=%s pnr=%s", order.id, order.booking_reference)
    return order


def get_booking(order_id: str, *, repository: OrderRepository | None = None) -> Order:
    repo = repository or OrderRepository()
    order = repo.get(order_id)
    if order is None:
        raise BookingNotFoundError(f"no booking with id {order_id}")
    return order
