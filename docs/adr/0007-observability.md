# ADR 0007 — Observability: metrics, structured logs, error tracking

**Status:** Accepted (Phase 4)

## Context
To run this safely we need to *see* it: how much/how often (metrics), what
happened (logs), and what's breaking now (errors) — the three pillars (Q35). In
travel, logs and error payloads also carry PII that must not leak (Q34).

## Decision
- **Metrics — Prometheus.** A `/metrics` endpoint exposes counters/histograms:
  HTTP request rate + latency (a middleware), plus domain signals — searches,
  provider degradations, bookings, tickets issued, outbox events relayed. Grafana
  (auto-provisioned datasource + a starter dashboard) visualizes them. **Kafka
  consumer lag** is scraped from Redpanda's own metrics, not re-implemented.
- **Logs — structured JSON + correlation id.** A `ContextVar` holds a per-request
  correlation id (set by middleware, echoed as `X-Correlation-ID`); a logging
  filter stamps it on every record and a JSON formatter emits it. One request is
  greppable across the log stream (and, via Kafka headers, across services).
  `LOG_JSON=false` keeps human-readable logs in dev.
- **Errors — Sentry, PII-scrubbed.** `before_send` recursively redacts passenger
  names, emails, documents, etc. Sentry is **off unless `SENTRY_DSN` is set**, so
  dev/test never phone home.

## Consequences
- SLO signals (latency, error rate, consumer lag) are visible on a dashboard;
  alerting is a Grafana/Prometheus rule away.
- Correlation ids make multi-service debugging tractable now and set up distributed
  tracing (OpenTelemetry → Jaeger/Tempo) later.
- PII scrubbing is centralized in one tested function — the safe default.
- The metrics middleware adds negligible overhead; cardinality is kept low (label
  by view name, not raw path).
