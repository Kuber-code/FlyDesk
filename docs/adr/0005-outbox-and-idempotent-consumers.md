# ADR 0005 — Transactional outbox + idempotent consumers

**Status:** Accepted (Phase 3)

## Context
After a booking is confirmed we want to trigger ticketing, notifications, and
audit — independently, retryably, and without coupling them to the booking
request. That's a job for events (Kafka). But the **dual-write problem** bites: we
can't atomically write the order to Mongo *and* publish to Kafka — a crash between
the two would lose or fabricate an event (interview Q30).

## Decision
- **Outbox embedded in the order document.** The `BookingConfirmed` event is
  written into the order's `outbox[]` array in the *same* single-document write as
  the order itself. MongoDB single-document writes are atomic, so the state change
  and the event-exists fact cannot diverge — no multi-document transaction needed.
- **A relay** (`relay_outbox` command) polls for orders with unpublished outbox
  events, publishes each to Kafka (Redpanda in dev), and stamps `published_at`.
  Publish-then-mark isn't atomic, so a crash can re-publish: that's **at-least-once**.
- **Idempotent consumers.** Every consumer records `(consumer, event_id)` under a
  unique index the first time it processes an event; a duplicate is a no-op. So
  redelivery never issues a second ticket or writes a second audit row (Q21/Q31).
- **Partition key = order id**, so all events for one booking keep their order (Q22).

## Consequences
- Reliable event emission without distributed transactions; the whole flow is
  unit-tested broker-free (relay + each consumer), with Redpanda only needed to
  run it live.
- Eventual consistency: `CONFIRMED` (sync) → `TICKETED` (async, via the consumer).
  The API exposes these states honestly.
- The relay's polling adds latency/load vs CDC (e.g. Debezium); fine at this scale,
  and the seam (the outbox) is the same if we later swap the poller for CDC.
- **Next:** a booking **saga** (reserve → pay → ticket) with compensation
  (void/refund) for when a downstream step fails after payment.
