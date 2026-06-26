# ADR 0003 — MongoDB via a repository, not the Django ORM

**Status:** Accepted (Phase 1)

## Context
The role uses **Django + MongoDB**. Django's ORM targets relational databases;
the community Mongo-ORM bridges are partial and add risk. Orders/itineraries are
naturally **document-shaped** and read as one unit.

## Decision
Use Django + DRF for the **HTTP layer** (routing, request validation, auth later,
admin). Persist domain documents to **MongoDB through a thin repository**
(`flydesk/bookings/repository.py`) using `pymongo`. Django's own ORM (SQLite here)
backs only Django internals (auth, sessions, admin).

Document modelling: an `order` **embeds** its `slices`/`segments`/`passengers`
because that's how it's read (one document, one read). Shared/dictionary data
(airline, airport) stays as **codes** (IATA), not duplicated sub-documents.

## Consequences
- Each tool does what it's good at; no fighting an ORM to speak Mongo.
- The repository is the only code that knows the document shape; the rest of the
  app stays in domain terms and is trivially testable with `mongomock`.
- Embedding fits the read pattern (interview Q11) and keeps documents well under
  the 16 MB limit.
- Phase 2 can introduce `motor` (async) behind the same repository seam for the
  hot paths without touching callers.
- Trade-off: no cross-document ACID by default — acceptable because a booking is
  one document; multi-step consistency is handled by the saga/outbox in Phase 3.
