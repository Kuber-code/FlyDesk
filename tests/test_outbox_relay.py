"""Transactional outbox + relay: publish-once, mark, and don't re-publish."""

from flydesk.bookings.repository import OrderRepository
from flydesk.domain import BookingPassenger, OutboxEvent
from flydesk.events.publisher import InMemoryEventPublisher
from flydesk.events.relay import relay_once
from flydesk.events.topics import BOOKINGS_CONFIRMED
from flydesk.providers.duffel import mapper, schemas


def _order_with_outbox(load, payload):
    data = schemas.DuffelOrderResponse.model_validate(
        load("duffel", "order_create_response.json")
    ).data
    order = mapper.map_order(data, [BookingPassenger(**payload)])
    event = OutboxEvent(
        id="evt-1",
        type="BookingConfirmed",
        payload={"order_id": order.id, "booking_reference": order.booking_reference},
    )
    return order.model_copy(update={"outbox": [event]})


async def test_relay_publishes_then_marks_and_does_not_republish(
    load, mongo_collection, adult_passenger_payload
):
    repo = OrderRepository(collection=mongo_collection)
    repo.save(_order_with_outbox(load, adult_passenger_payload))

    publisher = InMemoryEventPublisher()
    published = await relay_once(publisher, repository=repo)

    assert published == 1
    topic, key, value = publisher.published[0]
    assert topic == BOOKINGS_CONFIRMED
    assert value["type"] == "BookingConfirmed"
    assert value["id"] == "evt-1"

    # outbox event is now marked published
    stored = repo.get(value["payload"]["order_id"])
    assert stored.outbox[0].published_at is not None

    # a second relay finds nothing new
    assert await relay_once(publisher, repository=repo) == 0
    assert len(publisher.published) == 1
