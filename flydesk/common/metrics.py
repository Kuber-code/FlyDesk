"""
Prometheus metrics (the "how much / how often" pillar — interview Q35).

Defined once at import (the default registry). Scraped at `/metrics`; the key
SLO signals are HTTP latency/error rate, plus domain counters (searches, provider
degradations, bookings, tickets, outbox relayed). Kafka **consumer lag** is read
straight from the broker by Prometheus' kafka exporter / Redpanda metrics.
"""

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "flydesk_http_requests_total", "HTTP requests", ["method", "view", "status"]
)
HTTP_LATENCY = Histogram(
    "flydesk_http_request_duration_seconds", "HTTP request latency", ["method", "view"]
)

SEARCHES = Counter("flydesk_searches_total", "Search requests served", ["cached"])
PROVIDER_DEGRADED = Counter(
    "flydesk_provider_degraded_total", "Provider degradations during search", ["provider"]
)
BOOKINGS = Counter("flydesk_bookings_total", "Bookings created")
TICKETS_ISSUED = Counter("flydesk_tickets_issued_total", "Tickets issued by the ticketing consumer")
OUTBOX_PUBLISHED = Counter("flydesk_outbox_published_total", "Outbox events relayed to Kafka")
