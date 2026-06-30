# Deployment & rollout plan

Two things live here: **how to run, publish, and deploy the stack** and a record of
**how Phases 1–4 rolled out** (all now ✅ done). Pick the depth you need.

---

## TL;DR

1. Run the **whole stack** locally with `docker compose up --build` (API + Mongo +
   Redis + Redpanda + relay + worker + Prometheus + Grafana).
2. `git init` → push to a **public** GitHub repo. CI (`.github/workflows/ci.yml`)
   runs ruff + black + tests on every push.
3. Deploy to **Coolify** (recommended — you self-host it), pointed at the GitHub
   repo, with MongoDB + Redis + Kafka resources and env vars. HTTPS is automatic.
4. Phases 1–4 are all done; the seams described in the rollout plan are now built.

---

## 1. Run locally

```bash
cp .env.example .env          # set DUFFEL_API_TOKEN=duffel_test_…
docker compose up --build     # http://localhost:8000  (full stack)
```
This brings up the API on `:8000`, **Grafana** `:3000` (anonymous, FlyDesk
dashboard), **Prometheus** `:9090`, Mongo, Redis, Redpanda (Kafka API), plus the
`relay` (outbox → Kafka) and `worker` (idempotent consumers). App metrics live at
`:8000/metrics`. Or the venv path in the
[README](../README.md#option-b--local-venv). Smoke test:
```bash
curl localhost:8000/healthz
curl localhost:8000/metrics
pytest -q
```

## 2. Publish to GitHub (public)

```bash
git init -b main
git add .
git commit -m "FlyDesk Phase 1: provider-agnostic flight search & booking"
gh repo create flydesk --public --source=. --remote=origin --push
# or: create the repo in the UI, then:
# git remote add origin https://github.com/<you>/flydesk.git && git push -u origin main
```
`.gitignore` already excludes `.env`, `.venv`, `db.sqlite3`. **Never commit a real
token** — even a `duffel_test_` one. Confirm with `git status` before the first push.

## 3. CI

`.github/workflows/ci.yml` runs on every push/PR: `ruff check` → `black --check`
→ `manage.py check` → `pytest`. The suite is hermetic (respx mocks HTTP, mongomock
fakes Mongo), so CI needs no services and finishes in seconds. Add the green badge
to the README once it runs.

## 4. Production hardening checklist

Before exposing it publicly, set via env (not code):
- [ ] `DJANGO_DEBUG=false`
- [ ] `DJANGO_SECRET_KEY=<50+ random chars>`
- [ ] `DJANGO_ALLOWED_HOSTS=<your-domain>`
- [ ] `DUFFEL_API_TOKEN=duffel_test_…` (keep it a **test** token in a public demo)
- [ ] `MONGO_URI` points at a real, **non-public** MongoDB with auth
- [ ] `REDIS_URL` points at a real Redis (offer cache + idempotency reservation)
- [ ] `KAFKA_BOOTSTRAP_SERVERS` points at your broker (Redpanda/Kafka) for the
      relay + consumers
- [ ] `LOG_JSON=true` for structured logs; `SENTRY_DSN=<dsn>` to ship PII-scrubbed
      errors
- [ ] `PROMETHEUS_MULTIPROC_DIR=/tmp/prom` set for the web service so the gunicorn
      workers' `/metrics` aggregate correctly
- [ ] TLS terminated at the proxy (Coolify/Traefik does this automatically)
- [ ] `/healthz` wired as the platform health check
- [ ] gunicorn workers tuned (`--workers = 2×CPU+1`); the Dockerfile defaults to 3

Static files for the admin are collected at image build (`collectstatic`); for a
heavier setup add WhiteNoise or serve them from the proxy.

## 5. Deploy — recommended: Coolify

You already run Coolify, so it's the cheapest path and gives you Git-push deploys
plus automatic HTTPS.

The full stack is now multiple processes (web + relay + worker) plus Mongo, Redis
and Kafka. The **simplest** path is to deploy the committed `docker-compose.yml` as
a single *Docker Compose* resource (it already wires web/relay/worker/Mongo/Redis/
Redpanda/Prometheus/Grafana together). If you'd rather wire resources by hand:

1. **MongoDB** — in Coolify: *New Resource → Database → MongoDB*. Note its
   **internal** connection URL (e.g. `mongodb://<user>:<pass>@<service>:27017`).
2. **Redis** — *New Resource → Database → Redis*. Note its internal URL.
3. **Kafka/Redpanda** — add a Redpanda service (or point at an existing broker).
4. **App (web)** — *New Resource → Application → from your GitHub repo*. Build pack:
   **Dockerfile** (already in the repo). Port **8000**. The image's default `CMD`
   runs `migrate` then `gunicorn`.
5. **Relay + worker** — two more Applications from the **same image/repo**, with
   commands `python manage.py relay_outbox` and `python manage.py consume_events`
   respectively (no public port; they just need Mongo + Kafka).
6. **Env vars** — set the hardening list above; point `MONGO_URI`, `REDIS_URL` and
   `KAFKA_BOOTSTRAP_SERVERS` at the resources above, plus `MONGO_DB=flydesk`,
   `FLYDESK_PROVIDER=duffel`.
7. **Domain + health check** — assign a domain to *web* (Coolify provisions Let's
   Encrypt), set the health check path to `/healthz`.
8. **Deploy.** Each `git push` to `main` redeploys all three app services.

> If you deploy the compose file, remove the public `27017:27017` / `6379:6379` /
> `9092:9092` mappings and add real volumes/credentials — the committed compose is
> dev-oriented. Prometheus + Grafana ship in it too; drop them if your platform
> already provides monitoring.

**Managed Mongo option:** MongoDB **Atlas** has a free M0 tier. Create a cluster,
allowlist the server IP, and use its `mongodb+srv://…` string as `MONGO_URI` —
then the app needs no Mongo container at all.

## 6. Deploy — alternatives

- **Fly.io / Railway / Render** — all detect the Dockerfile; set the same env vars
  and attach a Mongo (Atlas, or the platform's add-on). Good if you don't want to
  self-host.
- **Plain VPS** — `git pull` + `docker compose up -d` behind Caddy/Traefik/Nginx
  for TLS. Simplest mental model; you own the box and updates.

---

## 7. Phased rollout — all phases ✅ done

Each phase was built to be independently demo-able. All four are now in this repo;
the checkpoints below describe what's shipped.

### Phase 1 — ✅ done
Django+DRF, Pydantic ACL, Mongo repository, Duffel live, Amadeus modelled,
idempotent bookings. **Checkpoint:** `search → book → fetch` works against the
Duffel sandbox; suite green in CI.

### Phase 2 — ✅ async + Redis + resilience
- **Search** runs on an async path: `httpx.AsyncClient`, `asyncio.gather` with a
  **`Semaphore`** and a per-provider `asyncio.timeout`; one slow/dead provider is
  skipped while the rest still return (graceful degradation).
- **Redis**: offer cache with TTL = offer validity; **idempotency-key reservation**
  (SETNX) before the provider call.
- **Retry + backoff + jitter** and a **circuit breaker** around provider calls.
- **Checkpoint:** "one provider dies, the rest still return results" —
  see `tests/test_async_search.py`, `test_resilience.py`, `test_search_cache.py`.

### Phase 3 — ✅ Kafka + saga + outbox
- On confirm, an **outbox** record is written **embedded in the order doc, atomic
  with the write**; the `relay_outbox` management command publishes to
  **Kafka/Redpanda**.
- **Idempotent consumers** (`consume_events`): Ticketing (`CONFIRMED → TICKETED`),
  Notifications, Audit. A duplicate event is a no-op (no second ticket).
- **Saga** in booking: reserve → (mock) pay → ticket, with **compensation** on
  failure (void/refund).
- **Checkpoint:** an event flows through 3 consumers; a replayed event is a no-op —
  see `tests/test_outbox_relay.py`, `test_consumers.py`, `test_saga.py`.

### Phase 4 — ✅ observability + CI/CD hardening
- **Sentry** with **PII scrubbing** (passenger names/documents), gated on
  `SENTRY_DSN`.
- **Prometheus** `/metrics` (HTTP + domain counters, multiprocess-aggregated under
  gunicorn) + a provisioned **Grafana** dashboard; **correlation IDs** seeded by
  middleware flow through HTTP + Kafka headers into structured JSON logs
  (`LOG_JSON=true`).
- `docker-compose` brings up the whole stack (Redis, Redpanda, Prometheus,
  Grafana). GitHub Actions has been green since Phase 1.
- **Checkpoint:** `docker compose up` brings the whole stack; Grafana dashboard at
  `:3000`; green pipeline — see `tests/test_observability.py`.

> **Still open (nice-to-haves):** swap the in-suite fakes (respx/mongomock) for
> **testcontainers** on the integration tests; wire Kafka **consumer-lag** panels
> into Grafana.

## 8. Interview talking points this unlocks

- "Provider-agnostic by design — Duffel live because Amadeus Self-Service retires
  in 2026, but the Amadeus domain is modelled behind the same port."
- "Pydantic is my anti-corruption layer — two very different GDS shapes, one domain
  model; malformed upstream data fails at the edge."
- "Bookings are idempotent — read-dedup + a unique index now, Redis key reservation
  next; re-price before book so we never sell a stale fare."
- "Django for HTTP, Mongo for documents through a repository — I don't fight an ORM
  to speak Mongo; orders embed their slices because that's how they're read."
- "Async fan-out with graceful degradation, a circuit breaker, a transactional
  outbox → Kafka with idempotent consumers, and a booking saga with compensation —
  all built on the same seams (the port, the service layer, correlation IDs)."
- "Observable end-to-end: Prometheus `/metrics`, a Grafana dashboard, structured
  JSON logs with correlation IDs through HTTP and Kafka headers, PII-scrubbed Sentry."
