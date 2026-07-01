# FlyDesk — Demo Cockpit 🎛️

An **interactive interview demo** on top of FlyDesk. It shows the
`search → book → ticket` flow live: a page where you click **Search**, see
normalized offers, **Book** one, and watch it appear in the bookings view and
tick over to `ticketed` — with Grafana dashboards (metrics + logs) moving in real
time.

> **Separate entity, zero app changes.** Everything lives in `demo/`. It does
> **not** modify anything under `flydesk/`. It reuses the real code by *import*
> and swaps the provider for an offline `DemoProvider` at runtime. Delete the
> `demo/` folder and the base project is untouched.

## What it demonstrates

| Tab | Shows | Real code behind it |
|---|---|---|
| **Search & book** | Offers generated **per route/date**, normalized through the real ACL; Book creates a PNR | `demo/generate.py` → `providers/duffel/mapper.py`; `bookings/services.py::create_booking` |
| **Available flights (cache)** | The ephemeral offers sitting in Redis, with a live TTL countdown | same cache key as `search/cache.py` (`offers:<hash>`) |
| **Bookings (Mongo)** | Historical bookings, `pending→confirmed→ticketed` | MongoDB `orders`; ticketing via `events/consumers.py` (Kafka) |
| **How it works** | Run instructions + a button→code map | — |

Plus three **Grafana dashboards** (see below), **idempotency** ("Book twice / same
key" → one order), and the **Kafka path** (confirmed → ticketed happens
asynchronously via the real outbox relay + ticketing consumer).

## How it works (the trick)

- **Search** = `demo/generate.py` builds a **Duffel-shaped payload** from the actual
  search criteria (varied carriers, prices, times, direct vs 1-stop), seeded by
  `(origin, destination, date)` so different queries return different flights while
  the same query stays stable. It's fed through the *production* Pydantic
  anti-corruption layer into normalized `Offer`s, then written to Redis under the
  app's own key format with a longer TTL so ephemeral offers stay visible for a few
  minutes.
- **Book** = the genuine `create_booking` use-case, so you get real idempotency
  (Redis SETNX + unique Mongo index) and a real transactional-outbox event. The
  only swap is `get_provider` → an offline `DemoProvider` that builds the order
  from the seeded offer instead of calling Duffel. No token, no network.
- Because the order is written to the same Mongo the `relay`/`worker` watch, the
  real **outbox relay** publishes `BookingConfirmed` to Kafka and the real
  **ticketing consumer** flips the status to `ticketed`.

### Optional: live Duffel offers

By default Search is offline and deterministic. To pull **live** offers from the
Duffel sandbox instead, set `DEMO_LIVE_DUFFEL=1` and a valid `DUFFEL_API_TOKEN`
in the environment of the `demo` service — same ACL, same cache, only the source
changes (it falls back to the synthetic generator on any error). Booking stays
offline via `DemoProvider` either way, so the demo never creates real orders.

*Recommendation:* for an interview keep it **offline** — it's deterministic, needs
no token or network, and can't fail live. Live mode is there to show the seam is
real, not because the demo needs it.

## Observability (Grafana + Prometheus + Loki)

Three provisioned dashboards at **http://localhost:3001** (anonymous login):

- **FlyDesk — App & Business (RED)** — business counters (bookings, tickets,
  searches, cache-hit ratio), the RED method for HTTP (request rate, 4xx/5xx
  errors, p50/p90/p99 latency, filterable by endpoint), and the streaming path
  (outbox relayed, provider degradations, Kafka consumer lag). Has a `view`
  variable and a restart annotation.
- **FlyDesk — Infrastructure (Docker)** — per-container CPU, memory, network I/O,
  restarts and up/down, from a small `docker stats` exporter (cAdvisor can't see
  individual containers inside Docker Desktop's VM, so we read the Docker API).
- **FlyDesk — Logs (Loki)** — container logs shipped by Promtail, filterable by
  service, with an error-lines counter and an "errors only" stream.

The clicks on the cockpit drive all of it: search/book and watch the counters,
lag, and logs react live.

## Run it (local, Docker)

```bash
# from the repo root
docker compose -f demo/docker-compose.demo.yml up --build
```

This overlay is **self-contained**: it brings up the whole stack (Mongo, Redis,
Redpanda, web, relay, worker, Prometheus, Grafana, **Loki, Promtail, stats
exporter**) **plus** the demo. You do **not** also run the base
`docker compose up` — this is instead of it.

Then open:

- **http://localhost:8500** — the demo cockpit
- **http://localhost:3001** — Grafana → the three **FlyDesk — …** dashboards
- **http://localhost:9091** — Prometheus

> Grafana/Prometheus sit on `:3001` / `:9091` (not the usual `:3000` / `:9090`)
> and the infra host ports aren't published, so the overlay won't clash even if a
> base `docker compose up` is already running. Fully offline by default: no
> `DUFFEL_API_TOKEN` needed.

Tear down with:
```bash
docker compose -f demo/docker-compose.demo.yml down -v
```

## Suggested 2-minute walkthrough

1. **Search flights** → ~12 offers appear; change the route/date and search again → different flights.
2. **Available flights** tab → point at the shrinking TTL = offers are ephemeral.
3. **Book** on an offer → a new PNR shows in **Bookings** (`confirmed`).
4. Refresh after a few seconds → status flips to `ticketed` (Kafka consumer).
5. **Book twice (same key)** → still one booking = idempotency.
6. Switch to **Grafana** → App dashboard counters climbing, Logs dashboard streaming.

## Files

```
demo/
  app.py                       FastAPI backend (serves the page + /api + /metrics)
  demo_provider.py             offline bookable FlightProvider (reads seeded offer)
  generate.py                  per-criteria Duffel-shaped offer generator
  seed.py                      generate/fetch -> ACL -> Redis (the "Search" button)
  stats_exporter.py            per-container docker-stats -> Prometheus (infra dashboard)
  static/index.html            the single-page cockpit UI
  Dockerfile                   demo image (context = repo root)
  requirements.txt             fastapi + uvicorn + docker (on top of the repo's requirements)
  docker-compose.demo.yml      include base stack + demo, loki, promtail, stats-exporter
  prometheus.demo.yml          base scrape jobs + demo + stats-exporter targets
  promtail-config.yml          ships container logs to Loki over the Docker socket
  grafana-provisioning/        datasources (Prometheus + Loki) + the 3 dashboards
```
