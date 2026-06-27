# ADR 0006 — Booking saga with compensation

**Status:** Accepted (Phase 3)

## Context
A booking spans **reserve → pay → ticket**. These can't be one ACID transaction
(they cross a provider, a payment gateway, and ticketing). A failure *after* an
earlier step succeeded must not leave a half-finished booking — e.g. paid but not
ticketed, or reserved but not paid (interview Q29).

## Decision
Use an **orchestration saga**: a coordinator runs the steps in order; if a step
fails, it runs the **compensating actions for completed steps in reverse**:

| Step | Forward | Compensation |
|---|---|---|
| reserve | create order / hold at provider | **void** the reservation |
| pay | charge the payment gateway | **refund** the payment |
| ticket | issue the e-ticket | — (last step) |

`flydesk/bookings/saga.py` is a tiny generic `Saga` (steps + compensations) plus
`build_booking_saga(reservation, payment, ticketing)`; the three collaborators are
injected, so each path is unit-tested in isolation. Compensations are best-effort
(logged, never mask the original failure).

## Consequences
- No half-finished bookings: a payment failure voids the reservation; a ticketing
  failure refunds the payment *and* voids the reservation.
- Orchestration (vs the event **choreography** in ADR 0005) is easier to reason
  about for this correctness-critical write path; the project demonstrates both.
- Eventual consistency with explicit states; combined with idempotency, retries
  are safe.
- A real deployment would split reserve/pay using Duffel **hold orders** (reserve
  without paying, pay later); here pay/ticket are pluggable to keep the pattern
  testable without a real gateway.
