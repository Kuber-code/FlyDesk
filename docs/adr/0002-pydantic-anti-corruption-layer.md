# ADR 0002 — Pydantic as the anti-corruption layer

**Status:** Accepted (Phase 1)

## Context
GDS/airline payloads are large, inconsistent, and provider-specific. Duffel is
`snake_case` with cabin class nested under `segment.passengers[]`; Amadeus is
`camelCase` and pushes carrier/aircraft names into a top-level `dictionaries`
block keyed by code. Letting either shape flow into the app would couple business
logic to provider quirks and leak `None`s on malformed data.

## Decision
Every provider response is parsed by **Pydantic v2** models of that provider's
*raw* shape (`schemas.py`, `extra="ignore"`), then mapped by pure functions
(`mapper.py`) into one normalized domain model (`flydesk/domain/`). DRF serializers
validate the **HTTP shape** of inbound requests; Pydantic enforces **domain
invariants** (IATA format, `return_date >= departure_date`, money as `Decimal`).

## Consequences
- Malformed upstream data fails fast **at the edge** with a precise error, not
  deep in a view.
- `extra="ignore"` on raw schemas means new provider fields can't break us; we
  parse only what we map.
- Domain models with computed fields (`stops`, `total_stops`) use `extra="ignore"`
  so they survive a `model_dump → store → model_validate` round-trip (Mongo now,
  Redis offer-cache in Phase 2). Leaf models keep `extra="forbid"` to catch mapper
  bugs.
- Two validation layers (DRF + Pydantic) is intentional, not redundant: different
  jobs, different failure messages.
