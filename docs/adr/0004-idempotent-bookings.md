# ADR 0004 — Idempotent bookings

**Status:** Accepted (Phase 1), strengthened in Phase 2

## Context
Booking is a **non-idempotent write**: a network retry, a double-click, or (later)
an at-least-once event redelivery must never create two orders or charge twice.
Search is a safe read and can be retried freely; writes cannot.

## Decision
The client sends an **`Idempotency-Key`** header on `POST /bookings`. Phase 1:
- look up an existing order by key before calling the provider; if found, replay it;
- a **unique (sparse) Mongo index** on `idempotency_key` makes a duplicate insert
  fail, and we resolve the race by returning the winner's order.

Phase 2 strengthens this by **reserving the key in Redis (SETNX + TTL) before**
the provider call, closing the small window where two concurrent requests could
both reach the provider.

## Consequences
- Safe retries and double-submits; the booking path has clear `pending → confirmed`
  states (interview Q31).
- Re-pricing happens inside `create_order` (GET the offer, pay the exact current
  amount) — we never book a stale price (interview Q40).
- Phase 1's guarantee is "no duplicate **persisted** order"; the rare double
  *provider* call under concurrency is removed in Phase 2 with the Redis reservation.
