"""
Seed the offer cache — the demo's "Search" button.

Offers are generated *per search criteria* (see generate.py) so changing the
route or date returns different flights, then fed through the production
anti-corruption layer (flydesk/providers/duffel/{schemas,mapper}.py) into
normalized `Offer`s and written to Redis under the SAME key format the app uses
(flydesk/search/cache.py: `offers:<sha1(criteria)>`), with a longer TTL so the
ephemeral offers stay visible for a few minutes during the demo.

Default is offline + deterministic (no token). Set `DEMO_LIVE_DUFFEL=1` with a
`DUFFEL_API_TOKEN` to fetch **live** offers from the Duffel sandbox instead —
same ACL, same cache, only the source changes (falls back to synthetic on error).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta

from demo import generate
from demo.demo_provider import OFFER_KEY
from flydesk.common import metrics, redis_client
from flydesk.domain import Offer, SearchCriteria
from flydesk.providers.duffel import mapper, schemas

logger = logging.getLogger("demo.seed")

DEMO_OFFER_TTL = int(os.environ.get("DEMO_OFFER_TTL", "300"))  # seconds
LIVE_DUFFEL = os.environ.get("DEMO_LIVE_DUFFEL") == "1"


def cache_key(criteria: SearchCriteria) -> str:
    """Identical to flydesk/search/cache.py::_cache_key — same key the app uses."""
    digest = hashlib.sha1(criteria.model_dump_json().encode()).hexdigest()
    return f"offers:{digest}"


def _synthetic_offers(criteria: SearchCriteria) -> list[Offer]:
    raw = generate.build_offer_request_payload(
        origin=criteria.origin,
        destination=criteria.destination,
        departure_date=criteria.departure_date,
        cabin_class=criteria.cabin_class.value,
        n_passengers=len(criteria.passengers),
    )
    parsed = schemas.DuffelOfferRequestResponse.model_validate(raw)
    return [mapper.map_offer(o) for o in parsed.data.offers]


def _live_offers(criteria: SearchCriteria) -> list[Offer]:
    """Real Duffel sandbox search through the production provider (opt-in)."""
    from flydesk.providers.duffel.client import DuffelProvider

    return DuffelProvider().search(criteria)


def _load_offers(criteria: SearchCriteria) -> list[Offer]:
    offers: list[Offer] | None = None
    if LIVE_DUFFEL:
        try:
            offers = _live_offers(criteria)
        except Exception as exc:  # network/token issue -> stay usable offline
            logger.warning("live_duffel_failed falling back to synthetic error=%r", exc)
    if not offers:
        offers = _synthetic_offers(criteria)
    # Give every offer a fresh, live TTL so the UI shows a real countdown.
    fresh_expiry = datetime.now(UTC) + timedelta(seconds=DEMO_OFFER_TTL)
    offers = [o.model_copy(update={"expires_at": fresh_expiry}) for o in offers]
    offers.sort(key=lambda o: o.total.amount)  # cheapest first, like the real search
    return offers


def seed(criteria: SearchCriteria) -> list[Offer]:
    """Run a 'trial search': generate/fetch offers, normalize, cache in Redis."""
    offers = _load_offers(criteria)
    r = redis_client.get_redis()
    key = cache_key(criteria)

    payload = [o.model_dump(mode="json") for o in offers]
    r.set(key, json.dumps(payload), ex=DEMO_OFFER_TTL)  # the bundle (app key format)
    r.sadd("demo:bundles", key)
    r.expire("demo:bundles", DEMO_OFFER_TTL)

    for offer in offers:  # per-offer lookup so booking can re-price offline
        r.set(
            OFFER_KEY.format(offer_id=offer.id),
            offer.model_dump_json(),
            ex=DEMO_OFFER_TTL,
        )

    metrics.SEARCHES.labels(cached="false").inc()
    return offers


def list_cached() -> list[dict]:
    """What's in the offer cache right now, with remaining TTL (the 'cache' tab)."""
    r = redis_client.get_redis()
    bundles: list[dict] = []
    for key in r.scan_iter("offers:*"):
        raw = r.get(key)
        if not raw:
            continue
        offers = json.loads(raw)
        bundles.append(
            {
                "key": key,
                "ttl_seconds": r.ttl(key),
                "count": len(offers),
                "offers": offers,
            }
        )
    return bundles
