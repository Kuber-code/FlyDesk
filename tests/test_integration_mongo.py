"""
Integration tests against a REAL MongoDB, spun up with testcontainers.

Why this exists: the hermetic suite fakes Mongo with mongomock, which cannot
faithfully enforce a unique index — so it proves idempotency via read-dedup only.
The actual race guard (interview Q31) is the **unique index on `idempotency_key`**,
and the only way to prove it bites is against a real `mongod`. These tests do that.

Opt-in: marked `integration`, excluded from the default run, and skipped cleanly
when Docker/testcontainers is unavailable. Run with:  `pytest -m integration`
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def real_orders():
    """A real `orders` collection backed by a throwaway mongo:7 container."""
    pytest.importorskip("testcontainers.mongodb")
    from pymongo import MongoClient
    from testcontainers.mongodb import MongoDbContainer

    container = MongoDbContainer("mongo:7")
    try:
        container.start()
    except Exception as exc:  # Docker not running / image pull blocked
        pytest.skip(f"Docker/testcontainers unavailable: {exc}")

    client = MongoClient(container.get_connection_url())
    try:
        yield client["flydesk_test"]["orders"]
    finally:
        client.close()
        container.stop()


def test_unique_index_rejects_duplicate_idempotency_key(real_orders, monkeypatch):
    """Two inserts with the same idempotency_key: the second must be rejected by
    the unique index. mongomock lets this through; real mongod does not."""
    from pymongo.errors import DuplicateKeyError

    from flydesk.bookings import repository

    monkeypatch.setattr(repository, "orders_collection", lambda: real_orders)
    repository.ensure_order_indexes.cache_clear()
    repository.ensure_order_indexes()

    real_orders.insert_one({"_id": "ord_A", "idempotency_key": "dupe"})
    with pytest.raises(DuplicateKeyError):
        real_orders.insert_one({"_id": "ord_B", "idempotency_key": "dupe"})


def test_repository_round_trips_an_order_against_real_mongo(
    real_orders, load, adult_passenger_payload
):
    """A domain Order survives save → fetch through real pymongo unchanged."""
    from flydesk.bookings.repository import OrderRepository
    from flydesk.domain import BookingPassenger
    from flydesk.providers.duffel import mapper, schemas

    data = schemas.DuffelOrderResponse.model_validate(
        load("duffel", "order_create_response.json")
    ).data
    order = mapper.map_order(data, [BookingPassenger(**adult_passenger_payload)])

    repo = OrderRepository(collection=real_orders)
    repo.save(order)
    fetched = repo.get(order.id)

    assert fetched is not None
    assert fetched.id == order.id
    assert fetched.booking_reference == order.booking_reference
    assert fetched.passengers[0].family_name == order.passengers[0].family_name
