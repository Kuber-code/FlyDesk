"""
Booking saga (orchestration) with compensation — interview Q29.

`reserve -> pay -> ticket` as a sequence of local steps driven by a coordinator.
If any step fails, the already-completed steps are compensated in **reverse**
order (refund the payment, void the reservation), so we never leave a
half-finished booking (paid-but-not-ticketed, reserved-but-not-paid). Orchestration
is easier to reason about for a correctness-critical flow than choreography.

This is the *orchestration* variant; Phase 3's Kafka consumers are the
*choreography* variant (events trigger the next reaction). The steps are pluggable
so the pattern is unit-tested in isolation. A real deployment would split
reserve/pay using Duffel **hold orders** (reserve now, pay later).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from flydesk.domain import BookingPassenger, Money, Order

logger = logging.getLogger("flydesk.bookings.saga")


@dataclass
class SagaStep:
    name: str
    action: Callable[[dict], None]
    compensation: Callable[[dict], None] | None = None


class SagaError(Exception):
    def __init__(self, step: str, original: Exception):
        super().__init__(f"saga failed at step '{step}': {original!r}")
        self.step = step
        self.original = original


class Saga:
    """Runs steps forward; on failure, compensates completed steps in reverse."""

    def __init__(self, steps: list[SagaStep]):
        self._steps = steps

    def run(self, context: dict | None = None) -> dict:
        context = context if context is not None else {}
        completed: list[SagaStep] = []
        for step in self._steps:
            try:
                step.action(context)
            except Exception as exc:
                logger.warning(
                    "saga_step_failed step=%s error=%r; compensating %d step(s)",
                    step.name,
                    exc,
                    len(completed),
                )
                self._compensate(completed, context)
                raise SagaError(step.name, exc) from exc
            completed.append(step)
        return context

    @staticmethod
    def _compensate(completed: list[SagaStep], context: dict) -> None:
        for step in reversed(completed):
            if step.compensation is None:
                continue
            try:
                step.compensation(context)
            except Exception:  # compensation is best-effort; log and continue
                logger.exception("saga_compensation_failed step=%s", step.name)


# --------------------------------------------------------------------------- #
# Booking saga: the three steps + their compensations
# --------------------------------------------------------------------------- #


class ReservationService(Protocol):
    def reserve(self, offer_id: str, passengers: list[BookingPassenger]) -> Order: ...
    def void(self, provider_order_id: str) -> None: ...


class PaymentGateway(Protocol):
    def charge(self, amount: Money, *, reference: str) -> str: ...
    def refund(self, payment_id: str) -> None: ...


class TicketingService(Protocol):
    def issue(self, order: Order) -> Order: ...


def build_booking_saga(
    reservation: ReservationService,
    payment: PaymentGateway,
    ticketing: TicketingService,
) -> Saga:
    def _reserve(ctx: dict) -> None:
        ctx["order"] = reservation.reserve(ctx["offer_id"], ctx["passengers"])

    def _void(ctx: dict) -> None:
        order = ctx.get("order")
        if order is not None:
            reservation.void(order.provider_order_id)

    def _pay(ctx: dict) -> None:
        order = ctx["order"]
        ctx["payment_id"] = payment.charge(order.total, reference=order.id)

    def _refund(ctx: dict) -> None:
        payment_id = ctx.get("payment_id")
        if payment_id is not None:
            payment.refund(payment_id)

    def _ticket(ctx: dict) -> None:
        ctx["order"] = ticketing.issue(ctx["order"])

    return Saga(
        [
            SagaStep("reserve", _reserve, _void),
            SagaStep("pay", _pay, _refund),
            SagaStep("ticket", _ticket, None),
        ]
    )
