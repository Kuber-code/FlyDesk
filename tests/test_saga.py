"""Booking saga: happy path runs all steps; a failure compensates in reverse."""

import pytest

from flydesk.bookings.saga import Saga, SagaError, SagaStep, build_booking_saga
from flydesk.domain import BookingPassenger, Order
from flydesk.domain.enums import OrderStatus
from flydesk.providers.duffel import mapper, schemas


def _order(load) -> Order:
    data = schemas.DuffelOrderResponse.model_validate(
        load("duffel", "order_create_response.json")
    ).data
    return mapper.map_order(
        data,
        [
            BookingPassenger(
                given_name="A",
                family_name="B",
                born_on="1990-01-01",
                email="a@b.c",
                phone_number="+1",
            )
        ],
    )


class FakeReservation:
    def __init__(self, order):
        self._order = order
        self.voided: list[str] = []

    def reserve(self, offer_id, passengers):
        return self._order

    def void(self, provider_order_id):
        self.voided.append(provider_order_id)


class FakePayment:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.charged: list[str] = []
        self.refunded: list[str] = []

    def charge(self, amount, *, reference):
        if self.fail:
            raise RuntimeError("card declined")
        self.charged.append(reference)
        return "pay_1"

    def refund(self, payment_id):
        self.refunded.append(payment_id)


class FakeTicketing:
    def __init__(self, *, fail=False):
        self.fail = fail

    def issue(self, order):
        if self.fail:
            raise RuntimeError("ticketing down")
        return order.model_copy(update={"status": OrderStatus.TICKETED})


def test_happy_path_runs_all_steps(load):
    order = _order(load)
    reservation, payment, ticketing = FakeReservation(order), FakePayment(), FakeTicketing()
    saga = build_booking_saga(reservation, payment, ticketing)

    ctx = saga.run({"offer_id": "off_x", "passengers": []})

    assert ctx["order"].status is OrderStatus.TICKETED
    assert payment.charged == [order.id]
    assert payment.refunded == [] and reservation.voided == []


def test_payment_failure_voids_reservation(load):
    order = _order(load)
    reservation, payment, ticketing = (
        FakeReservation(order),
        FakePayment(fail=True),
        FakeTicketing(),
    )
    saga = build_booking_saga(reservation, payment, ticketing)

    with pytest.raises(SagaError) as exc:
        saga.run({"offer_id": "off_x", "passengers": []})

    assert exc.value.step == "pay"
    assert reservation.voided == [order.provider_order_id]  # reserve compensated
    assert payment.refunded == []  # nothing to refund — pay never completed


def test_ticketing_failure_refunds_and_voids(load):
    order = _order(load)
    reservation, payment, ticketing = (
        FakeReservation(order),
        FakePayment(),
        FakeTicketing(fail=True),
    )
    saga = build_booking_saga(reservation, payment, ticketing)

    with pytest.raises(SagaError) as exc:
        saga.run({"offer_id": "off_x", "passengers": []})

    assert exc.value.step == "ticket"
    assert payment.refunded == ["pay_1"]  # pay compensated
    assert reservation.voided == [order.provider_order_id]  # reserve compensated


def test_compensations_run_in_reverse_order():
    order_of_calls: list[str] = []
    steps = [
        SagaStep(
            "a", lambda c: order_of_calls.append("do-a"), lambda c: order_of_calls.append("undo-a")
        ),
        SagaStep(
            "b", lambda c: order_of_calls.append("do-b"), lambda c: order_of_calls.append("undo-b")
        ),
        SagaStep("c", lambda c: (_ for _ in ()).throw(RuntimeError("boom"))),
    ]
    with pytest.raises(SagaError):
        Saga(steps).run({})
    assert order_of_calls == ["do-a", "do-b", "undo-b", "undo-a"]
