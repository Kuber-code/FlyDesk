"""Idempotent consumers: a replayed event never double-tickets or double-writes."""

import mongomock

from flydesk.bookings.repository import OrderRepository
from flydesk.domain import BookingPassenger
from flydesk.domain.enums import OrderStatus
from flydesk.events.consumers import handle_audit, handle_notification, handle_ticketing
from flydesk.events.dedupe import ProcessedEvents
from flydesk.events.publisher import InMemoryEventPublisher
from flydesk.providers.duffel import mapper, schemas


def _confirmed_order(load, payload):
    data = schemas.DuffelOrderResponse.model_validate(
        load("duffel", "order_create_response.json")
    ).data
    return mapper.map_order(data, [BookingPassenger(**payload)])


def _processed():
    return ProcessedEvents(collection=mongomock.MongoClient()["t"]["processed_events"])


async def test_ticketing_is_idempotent(load, mongo_collection, adult_passenger_payload):
    repo = OrderRepository(collection=mongo_collection)
    order = _confirmed_order(load, adult_passenger_payload)
    repo.save(order)

    dedupe = _processed()
    publisher = InMemoryEventPublisher()
    event = {"id": "evt-9", "type": "BookingConfirmed", "payload": {"order_id": order.id}}

    did = await handle_ticketing(event, repository=repo, dedupe=dedupe, publisher=publisher)
    assert did is True
    assert repo.get(order.id).status is OrderStatus.TICKETED
    assert len(publisher.published) == 1  # one TicketIssued
    assert publisher.published[0][2]["type"] == "TicketIssued"

    # redelivery of the SAME event — no second ticket, no second publish
    again = await handle_ticketing(event, repository=repo, dedupe=dedupe, publisher=publisher)
    assert again is False
    assert repo.get(order.id).status is OrderStatus.TICKETED
    assert len(publisher.published) == 1


async def test_notification_and_audit_are_idempotent():
    dedupe = _processed()
    audit = mongomock.MongoClient()["t"]["audit_log"]
    event = {"id": "evt-7", "type": "BookingConfirmed", "payload": {"order_id": "ord_x"}}

    assert await handle_notification(event, dedupe=dedupe) is True
    assert await handle_notification(event, dedupe=dedupe) is False

    assert await handle_audit(event, dedupe=dedupe, audit_collection=audit) is True
    assert await handle_audit(event, dedupe=dedupe, audit_collection=audit) is False
    assert audit.count_documents({}) == 1  # written exactly once
