"""
Idempotent consumers of `BookingConfirmed` (interview Q21/Q23).

- **ticketing**: CONFIRMED -> TICKETED, then emits `TicketIssued`. A replayed
  event must never issue a second ticket.
- **notifications**: side-effect (here: a log line / email-mock).
- **audit**: appends the event to an audit log.

Each is independent and idempotent — the point of decoupling via Kafka: add a
consumer without touching the producer, and at-least-once redelivery is safe.
"""

import logging
import uuid
from datetime import UTC, datetime

from pymongo.collection import Collection

from flydesk.bookings.repository import OrderRepository
from flydesk.domain import OrderEvent
from flydesk.domain.enums import OrderStatus
from flydesk.events.dedupe import ProcessedEvents
from flydesk.events.publisher import EventPublisher
from flydesk.events.topics import TICKETS_ISSUED

logger = logging.getLogger("flydesk.events.consumers")


async def handle_ticketing(
    event: dict,
    *,
    repository: OrderRepository,
    dedupe: ProcessedEvents,
    publisher: EventPublisher,
    consumer: str = "ticketing",
) -> bool:
    """Returns True if work was done, False if it was a duplicate (no-op)."""
    if not dedupe.mark_if_new(event["id"], consumer=consumer):
        logger.info("duplicate_event_skipped consumer=%s id=%s", consumer, event["id"])
        return False

    order_id = event["payload"]["order_id"]
    order = repository.get(order_id)
    if order is None:
        logger.warning("ticketing_order_missing id=%s", order_id)
        return False

    if order.status is not OrderStatus.TICKETED:
        order = order.model_copy(
            update={
                "status": OrderStatus.TICKETED,
                "events": [
                    *order.events,
                    OrderEvent(type="ticket.issued", detail="e-ticket issued"),
                ],
            }
        )
        repository.save(order)

    await publisher.publish(
        TICKETS_ISSUED,
        key=order_id,
        value={
            "id": uuid.uuid4().hex,
            "type": "TicketIssued",
            "payload": {"order_id": order_id, "booking_reference": order.booking_reference},
        },
    )
    return True


async def handle_notification(
    event: dict, *, dedupe: ProcessedEvents, consumer: str = "notifications"
) -> bool:
    if not dedupe.mark_if_new(event["id"], consumer=consumer):
        return False
    payload = event["payload"]
    logger.info(
        "notification_sent order=%s pnr=%s (email-mock)",
        payload.get("order_id"),
        payload.get("booking_reference"),
    )
    return True


async def handle_audit(
    event: dict,
    *,
    dedupe: ProcessedEvents,
    audit_collection: Collection,
    consumer: str = "audit",
) -> bool:
    if not dedupe.mark_if_new(event["id"], consumer=consumer):
        return False
    audit_collection.insert_one(
        {
            "event_id": event["id"],
            "type": event["type"],
            "payload": event["payload"],
            "at": datetime.now(UTC),
        }
    )
    return True
