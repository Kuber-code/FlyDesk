# Deployment & rollout plan

Two things live here: **how to ship Phase 1** (run it, publish it, deploy it) and
**how to roll out Phases 2–4** over time. Pick the depth you need.

---

## TL;DR

1. Run locally with `docker compose up --build` (Mongo + app).
2. `git init` → push to a **public** GitHub repo. CI (`.github/workflows/ci.yml`)
   runs ruff + , pusblack + tests on every push.
3. Deploy the container to **Coolify** (recommended — you self-host it), pointed at
   the GitHub repo, with a MongoDB resource and env vars. HTTPS is automatic.
4. Build Phases 2–4 in order; each ends at a demo-able checkpoint.

---

## 1. Run locally

```bash
cp .env.example .env          # set DUFFEL_API_TOKEN=duffel_test_…
docker compose up --build     # http://localhost:8000  (Mongo + Django)
```
Or the venv path in the [README](../README.md#option-b--local-venv). Smoke test:
```bash
curl localhost:8000/healthz
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
- [ ] TLS terminated at the proxy (Coolify/Traefik does this automatically)
- [ ] `/healthz` wired as the platform health check
- [ ] gunicorn workers tuned (`--workers = 2×CPU+1`); the Dockerfile defaults to 3

Static files for the admin are collected at image build (`collectstatic`); for a
heavier setup add WhiteNoise or serve them from the proxy.

## 5. Deploy — recommended: Coolify

You already run Coolify, so it's the cheapest path and gives you Git-push deploys
plus automatic HTTPS.

1. **MongoDB** — in Coolify: *New Resource → Database → MongoDB*. Note its
   **internal** connection URL (e.g. `mongodb://<user>:<pass>@<service>:27017`).
2. **App** — *New Resource → Application → from your GitHub repo*. Build pack:
   **Dockerfile** (already in the repo). Port **8000**.
3. **Env vars** — set the hardening list above; point `MONGO_URI` at the database
   from step 1, `MONGO_DB=flydesk`, `FLYDESK_PROVIDER=duffel`.
4. **Domain + health check** — assign a domain (Coolify provisions Let's Encrypt),
   set the health check path to `/healthz`.
5. **Deploy.** Each `git push` to `main` redeploys. The container runs
   `migrate` then `gunicorn` (see the Dockerfile `CMD`).

> Alternatively deploy the whole `docker-compose.yml` as a *Docker Compose*
> resource. If you do, remove the public `27017:27017` mapping and add a real
> volume/credentials for Mongo — the committed compose is dev-oriented.

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

## 7. Phased rollout plan

Each phase is independently demo-able — you can stop after any one and still have
something coherent to show. Rough effort assumes part-time evenings.

### Phase 1 — ✅ done (this repo)
Django+DRF, Pydantic ACL, Mongo repository, Duffel live, Amadeus modelled,
idempotent bookings. **Checkpoint:** `search → book → fetch` works against the
Duffel sandbox; 23 tests green in CI.

### Phase 2 — async + Redis + resilience  (~1 week)
- Extract **Search** into an async path: `httpx.AsyncClient`/`aiohttp`,
  `asyncio.gather` with a **`Semaphore`**, per-request `asyncio.timeout`.
- Fan out to 2–3 providers (Duffel + mocks with different latency); aggregate.
- **Redis**: cache offers with TTL = offer validity; **reserve idempotency keys**
  (SETNX) before the provider call; rate-limit outbound calls.
- **Retry + backoff + jitter** and a **circuit breaker**; use Duffel's test routes
  that force timeouts / no offers to prove graceful degradation.
- **Checkpoint:** "one provider dies, the rest still return results" + a Resilience
  section in the README with logs/tests as proof.

### Phase 3 — Kafka + saga + outbox  (~1–2 weeks)
- On `CONFIRMED`, write an **outbox** record in the same transaction as the order;
  a relay publishes `BookingConfirmed` to **Kafka**.
- **Idempotent consumers** (`aiokafka`): Ticketing (`CONFIRMED → TICKETED`),
  Notifications, Audit. A duplicate event must not issue a second ticket.
- **Saga** in booking: reserve → (mock) pay → ticket, with **compensation** on
  failure (void/refund).
- **Checkpoint:** an event flows through 3 consumers; a replayed event is a no-op
  (shown by a test).

### Phase 4 — observability + CI/CD hardening  (~few days)
- **Sentry** in every service with **PII scrubbing** (passenger names/documents).
- **Prometheus/Grafana**: search latency, error rate, **Kafka consumer lag**;
  **correlation IDs** (already seeded by middleware) through HTTP + Kafka headers
  into structured JSON logs.
- Extend `docker-compose` (Redis, Kafka, Prometheus, Grafana); add **testcontainers**
  integration tests to CI.
- **Checkpoint:** `docker compose up` brings the whole stack; a Grafana dashboard;
  green pipeline.

## 8. Interview talking points this unlocks

- "Provider-agnostic by design — Duffel live because Amadeus Self-Service retires
  in 2026, but the Amadeus domain is modelled behind the same port."
- "Pydantic is my anti-corruption layer — two very different GDS shapes, one domain
  model; malformed upstream data fails at the edge."
- "Bookings are idempotent — read-dedup + a unique index now, Redis key reservation
  next; re-price before book so we never sell a stale fare."
- "Django for HTTP, Mongo for documents through a repository — I don't fight an ORM
  to speak Mongo; orders embed their slices because that's how they're read."
- "It's structured for async/Kafka/observability to slot in — the seams are already
  there (the port, the service layer, correlation IDs, the outbox-shaped order events)."
