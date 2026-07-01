# ADR 0008 — Interactive demo cockpit

**Status:** Accepted (Phase 4, tooling)

## Context
The project is a backend; its story (provider-agnostic search, ephemeral offers,
idempotent booking, outbox → Kafka → ticketing, observability) is easy to *tell*
but hard to *show* from `curl`. For interviews we want a click-through that makes
the flow tangible — and a way to demonstrate the Grafana dashboards moving — without
polluting the application or requiring a live Duffel token.

## Decision
Add a **self-contained demo** under [`demo/`](../../demo/) that reuses the real
code by import and never edits it:

- A tiny **FastAPI** cockpit (`demo/app.py`) serves a single-page UI with tabs for
  Search, the Redis offer cache (with a live TTL), and the Mongo booking history.
- **Search** = `demo/seed.py` runs the *production* anti-corruption layer over a
  captured Duffel fixture and writes normalized offers into Redis under the app's
  own key format (`offers:<hash>`), just with a longer TTL so ephemeral offers stay
  visible for a few minutes.
- **Book** goes through the genuine `flydesk.bookings.services.create_booking`
  (real idempotency + transactional outbox). The only change is a **runtime**
  swap of `get_provider` for an offline `DemoProvider` that builds the order from
  the seeded offer — no network, no token. Because the order lands in the same
  Mongo the `relay`/`worker` watch, the real outbox relay + ticketing consumer
  still flip `confirmed → ticketed` over Kafka.
- **Offers are generated per search criteria** (`demo/generate.py`): a
  Duffel-shaped payload built from `(origin, destination, date)` and fed through
  the *real* schemas + mapper, so changing route or date returns different flights
  (~12 per search) instead of a static fixture — while staying deterministic and
  offline. An opt-in `DEMO_LIVE_DUFFEL=1` path calls the real Duffel sandbox
  instead (same ACL), falling back to synthetic on error.
- Run via `demo/docker-compose.demo.yml`, which **`include`s** the base stack and
  only *adds* services. It publishes clash-proof ports (cockpit `:8500`, Grafana
  `:3001`, Prometheus `:9091`) and doesn't expose infra host ports, so it coexists
  with a running base stack.
- **Observability**, split the way a real setup would be: an **App & Business**
  dashboard (RED method + business counters + streaming/consumer-lag), an
  **Infrastructure** dashboard (per-container CPU/mem/net via a small `docker stats`
  exporter — cAdvisor can't see individual containers inside Docker Desktop's VM),
  and a **Logs** dashboard backed by **Loki + Promtail**.

## Consequences
- A 2-minute, offline, deterministic walkthrough of the full domain flow, with the
  dashboards visibly reacting — strong interview material.
- **Zero risk to the app:** no `flydesk/` source changes; deleting `demo/` leaves
  the project identical. The reuse-by-import approach means the demo exercises the
  *real* booking path, not a mock, so it can't drift into lying about behaviour.
- Trade-off: a second, small copy of one fixture to keep in sync, and a FastAPI
  dependency scoped to the demo image only (not the app).
- The `DemoProvider` skips real re-pricing (there's no live fare to re-fetch); the
  production Duffel path still does it inside `create_order` (see ADR 0004).
