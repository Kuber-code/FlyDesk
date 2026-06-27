"""
Booking use-cases.

Idempotency (interview Q31), now in two layers:
1. **Reserve** the idempotency key in Redis (SETNX + TTL) *before* calling the
   provider — this closes the window where two concurrent requests could both
   reach the provider and double-book.
2. **Dedup on read** + a **unique Mongo index** as the durable backstop (and the
   fallback if Redis is unavailable).

Re-pricing happens inside `provider.create_order` (GET the offer, pay the exact
current amount) so we never book a stale fare (interview Q40).
"""

import logging
import uuid

import redis
from pymongo.errors import DuplicateKeyError

from flydesk.common import redis_client
from flydesk.common.exceptions import BookingInProgressError, BookingNotFoundError
from flydesk.domain import BookingPassenger, Order, OutboxEvent
from flydesk.providers import get_provider

from .repository import OrderRepository, ensure_order_indexes

logger = logging.getLogger("flydesk.bookings")

RESERVATION_TTL = 120  # seconds


def _booking_confirmed_event(order: Order) -> OutboxEvent:
    """A BookingConfirmed event staged in the order's outbox, published later by
    the relay (interview Q30). Consumers (ticketing/notifications/audit) react."""
    return OutboxEvent(
        id=uuid.uuid4().hex,
        type="BookingConfirmed",
        payload={
            "order_id": order.id,
            "booking_reference": order.booking_reference,
            "provider": order.provider.value,
            "total": order.total.model_dump(mode="json"),
        },
    )


def _reserve(idempotency_key: str) -> bool:
    """True if we acquired the reservation. If Redis is down, don't block — the
    unique index still prevents a duplicate *persisted* order."""
    try:
        acquired = redis_client.get_redis().set(
            f"idem:{idempotency_key}", "1", nx=True, ex=RESERVATION_TTL
        )
        return bool(acquired)
    except redis.RedisError as exc:
        logger.warning("redis_unavailable_reserve error=%r", exc)
        return True


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
        if not _reserve(idempotency_key):
            # Someone else holds the reservation: return their result if it's
            # already persisted, otherwise tell the client it's in progress.
            existing = repo.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
            raise BookingInProgressError()

    passengers = [BookingPassenger(**p) for p in passengers_data]
    provider = get_provider(provider_name)

    order = provider.create_order(offer_id, passengers)
    # Stage the BookingConfirmed event in the SAME document write as the order
    # (transactional outbox) — the relay publishes it to Kafka afterwards.
    updates: dict = {"outbox": [_booking_confirmed_event(order)]}
    if idempotency_key:
        updates["idempotency_key"] = idempotency_key
    order = order.model_copy(update=updates)

    try:
        repo.save(order)
    except DuplicateKeyError:
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
