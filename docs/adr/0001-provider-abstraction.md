# ADR 0001 — Provider abstraction (`FlightProvider` port)

**Status:** Accepted (Phase 1)

## Context
The role/domain integrates with **Amadeus**, but Amadeus is retiring its public
**Self-Service** developer portal mid-2026, pushing new integrations to the
Enterprise track. Building a portfolio project directly on live Amadeus keys is
therefore fragile. **Duffel** offers a free sandbox with the same shop → price →
book flow and test routes that force timeouts / no-offers / connections.

## Decision
Introduce a single port — `FlightProvider` (`flydesk/providers/base.py`) — with
`search`, `get_offer` (re-price), and `create_order`. The rest of the app depends
only on this interface and the domain models. Concrete adapters:

- **`DuffelProvider`** — wired live (sync `httpx` in Phase 1).
- **`AmadeusProvider`** — modelled, not called live: full raw schemas + mapper
  that normalize a recorded Amadeus payload into the same `Offer`. Live methods
  raise `NotImplementedError` with an explanatory message.

A factory `get_provider()` resolves the implementation from `FLYDESK_PROVIDER`.

## Consequences
- We can demonstrate genuine Amadeus **domain** understanding (offers/PNR/segments,
  `dictionaries`) without depending on a portal that's going away.
- Swapping or adding providers (an NDC aggregator, a low-cost-carrier feed) is a
  new adapter, not a rewrite.
- The interface is the natural place for resilience (Phase 2): per-provider
  timeouts, semaphores, retries, circuit breakers — added once, behind the port.
- Cost: a normalization layer to maintain. Mitigated by pure, unit-tested mappers.
