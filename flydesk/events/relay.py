"""
Outbox relay (interview Q30).

Polls orders for outbox events that haven't been published, publishes each to
Kafka, and stamps `published_at`. Because publish-then-mark isn't atomic, a crash
between the two can re-publish an event — that's fine: it's **at-least-once**, and
consumers are idempotent (dedupe on event id), so a duplicate is harmless.
"""

import logging
from datetime import UTC, datetime

from flydesk.bookings.repository import OrderRepository
from flydesk.events.publisher import EventPublisher
from flydesk.events.topics import topic_for

logger = logging.getLogger("flydesk.events.relay")


async def relay_once(
    publisher: EventPublisher, *, repository: OrderRepository | None = None
) -> int:
    """Publish all pending outbox events once. Returns how many were published."""
    repo = repository or OrderRepository()
    published = 0

    for order in repo.find_with_unpublished_outbox():
        changed = False
        for event in order.outbox:
            if event.published_at is not None:
                continue
            await publisher.publish(
                topic_for(event.type),
                key=str(event.payload.get("order_id", order.id)),
                value={"id": event.id, "type": event.type, "payload": event.payload},
            )
            event.published_at = datetime.now(UTC)
            changed = True
            published += 1
        if changed:
            repo.save(order)

    if published:
        logger.info("outbox_relayed events=%d", published)
    return published
