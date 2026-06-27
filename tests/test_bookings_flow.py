"""Booking service: persistence to (in-memory) Mongo + idempotent replay."""

from flydesk.bookings import services
from flydesk.bookings.repository import OrderRepository
from flydesk.domain import BookingPassenger, Order
from flydesk.providers.duffel import mapper, schemas


class FakeProvider:
    """Returns a fixed domain Order and counts how often it's asked to book."""

    def __init__(self, order: Order):
        self._order = order
        self.create_calls = 0

    def create_order(self, offer_id, passengers):
        self.create_calls += 1
        return self._order


def _order_from_fixture(load, payload) -> Order:
    data = schemas.DuffelOrderResponse.model_validate(
        load("duffel", "order_create_response.json")
    ).data
    return mapper.map_order(data, [BookingPassenger(**payload)])


def test_booking_is_persisted_and_readable(
    load, mongo_collection, adult_passenger_payload, monkeypatch
):
    provider = FakeProvider(_order_from_fixture(load, adult_passenger_payload))
    monkeypatch.setattr(services, "get_provider", lambda name=None: provider)

    repo = OrderRepository(collection=mongo_collection)
    order = services.create_booking(
        offer_id="off_0000DirectBA01",
        passengers_data=[adult_passenger_payload],
        idempotency_key="idem-123",
        repository=repo,
    )

    stored = services.get_booking(order.id, repository=repo)
    assert stored.booking_reference == "345FKK"
    assert stored.idempotency_key == "idem-123"
    assert stored.passengers[0].family_name == "Stark"


def test_same_idempotency_key_does_not_double_book(
    load, mongo_collection, adult_passenger_payload, monkeypatch
):
    provider = FakeProvider(_order_from_fixture(load, adult_passenger_payload))
    monkeypatch.setattr(services, "get_provider", lambda name=None: provider)
    repo = OrderRepository(collection=mongo_collection)

    first = services.create_booking(
        offer_id="off_0000DirectBA01",
        passengers_data=[adult_passenger_payload],
        idempotency_key="idem-xyz",
        repository=repo,
    )
    second = services.create_booking(
        offer_id="off_0000DirectBA01",
        passengers_data=[adult_passenger_payload],
        idempotency_key="idem-xyz",
        repository=repo,
    )

    assert first.id == second.id
    assert provider.create_calls == 1  # the provider was hit only once


def test_get_unknown_booking_raises(mongo_collection):
    import pytest

    from flydesk.common.exceptions import BookingNotFoundError

    repo = OrderRepository(collection=mongo_collection)
    with pytest.raises(BookingNotFoundError):
        services.get_booking("ord_does_not_exist", repository=repo)


def test_held_reservation_returns_in_progress(
    load, mongo_collection, adult_passenger_payload, monkeypatch, fake_redis
):
    import pytest

    from flydesk.common.exceptions import BookingInProgressError

    provider = FakeProvider(_order_from_fixture(load, adult_passenger_payload))
    monkeypatch.setattr(services, "get_provider", lambda name=None: provider)
    repo = OrderRepository(collection=mongo_collection)

    # Another request already reserved the key (and hasn't persisted yet).
    fake_redis.set("idem:busy-key", "1")

    with pytest.raises(BookingInProgressError):
        services.create_booking(
            offer_id="off_x",
            passengers_data=[adult_passenger_payload],
            idempotency_key="busy-key",
            repository=repo,
        )
    assert provider.create_calls == 0  # never reached the provider


def test_booking_stages_outbox_event(load, mongo_collection, adult_passenger_payload, monkeypatch):
    provider = FakeProvider(_order_from_fixture(load, adult_passenger_payload))
    monkeypatch.setattr(services, "get_provider", lambda name=None: provider)
    repo = OrderRepository(collection=mongo_collection)

    order = services.create_booking(
        offer_id="off_x",
        passengers_data=[adult_passenger_payload],
        repository=repo,
    )

    stored = repo.get(order.id)
    assert len(stored.outbox) == 1
    assert stored.outbox[0].type == "BookingConfirmed"
    assert stored.outbox[0].published_at is None  # not yet relayed
