"""
FlyDesk demo cockpit — a tiny, self-contained FastAPI backend for the interview.

It does NOT modify the application. It reuses flydesk's real code by import:
- `seed.py` normalizes fixture payloads through the production ACL into Redis,
- booking goes through the genuine `flydesk.bookings.services.create_booking`
  (real idempotency + transactional outbox), with `get_provider` swapped at
  runtime for the offline `DemoProvider` — a runtime injection, not an edit.

Endpoints:
  GET  /                 -> the single-page cockpit (static/index.html)
  POST /api/search       -> "trial search": seed offers into Redis (extended TTL)
  GET  /api/cache        -> offers currently in the cache (with remaining TTL)
  POST /api/book         -> create a booking (appears under Rezerwacje)
  GET  /api/bookings     -> historical bookings, read straight from MongoDB
  GET  /metrics          -> Prometheus counters (so Grafana panels move)
  GET  /api/health
"""

from __future__ import annotations

# --- Configure Django first ------------------------------------------------- #
# flydesk.common.exceptions imports DRF, which needs Django settings loaded.
import os  # noqa: E402
import uuid
from datetime import date
from pathlib import Path

import django  # noqa: E402
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

# --- Runtime injection: make the real booking use-case book offline ---------- #
# create_booking() calls get_provider(); point that at the offline DemoProvider.
# This is done from the demo process only — flydesk/ source is untouched.
import flydesk.bookings.services as booking_services  # noqa: E402
from demo.demo_provider import DemoProvider  # noqa: E402

booking_services.get_provider = lambda name=None: DemoProvider()

from demo import seed  # noqa: E402
from flydesk.common.mongo import orders_collection  # noqa: E402
from flydesk.domain import Order, SearchCriteria  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"

DEMO_PASSENGER = {
    "type": "adult",
    "title": "mr",
    "gender": "m",
    "given_name": "Tony",
    "family_name": "Stark",
    "born_on": "1980-07-24",
    "email": "tony@stark.com",
    "phone_number": "+442080160508",
}

app = FastAPI(title="FlyDesk Demo Cockpit", docs_url="/api/docs")


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class SearchBody(BaseModel):
    origin: str = "LHR"
    destination: str = "JFK"
    departure_date: date = date(2026, 8, 15)


class BookBody(BaseModel):
    offer_id: str
    idempotency_key: str | None = None  # reused across clicks to show idempotency


def _criteria(body: SearchBody) -> SearchCriteria:
    return SearchCriteria(
        origin=body.origin,
        destination=body.destination,
        departure_date=body.departure_date,
    )


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/search")
def search(body: SearchBody) -> dict:
    """Trial search: seed the fixture offers into Redis (via the real ACL)."""
    criteria = _criteria(body)
    offers = seed.seed(criteria)
    return {
        "count": len(offers),
        "cache_key": seed.cache_key(criteria),
        "ttl_seconds": seed.DEMO_OFFER_TTL,
        "offers": [o.model_dump(mode="json") for o in offers],
    }


@app.get("/api/cache")
def cache() -> dict:
    bundles = seed.list_cached()
    return {"bundles": bundles}


@app.post("/api/book")
def book(body: BookBody) -> dict:
    """Book through the genuine create_booking use-case (idempotency + outbox)."""
    key = body.idempotency_key or uuid.uuid4().hex
    try:
        order = booking_services.create_booking(
            offer_id=body.offer_id,
            passengers_data=[DEMO_PASSENGER],
            idempotency_key=key,
        )
    except Exception as exc:  # surface the domain error to the UI
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc
    return {"idempotency_key": key, "order": order.model_dump(mode="json")}


@app.get("/api/bookings")
def bookings() -> dict:
    """Historical bookings — a straight read of the MongoDB orders collection."""
    docs = orders_collection().find().sort("created_at", -1).limit(50)
    orders = []
    for doc in docs:
        doc = dict(doc)
        doc["id"] = doc.pop("_id")
        orders.append(Order.model_validate(doc).model_dump(mode="json"))
    return {"count": len(orders), "bookings": orders}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
