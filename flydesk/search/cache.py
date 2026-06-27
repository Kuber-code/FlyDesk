"""
Cache-aside for search (interview Q16/Q17).

Search is expensive (fan-out to providers); offers are short-lived. So we cache
the normalized result under a key derived from the criteria, with a short TTL
matched to offer volatility, and always re-price before booking rather than
trusting the cache. If Redis is unavailable we **degrade to a live search** — the
cache is an optimization, never a dependency. Partial (degraded) results are not
cached, so we never serve a result with holes.
"""

import hashlib
import json
import logging

import redis
from asgiref.sync import async_to_sync

from flydesk.common import metrics, redis_client
from flydesk.common.config import get_settings
from flydesk.domain import Offer, SearchCriteria
from flydesk.providers.base import get_async_providers
from flydesk.search.async_service import search_all

logger = logging.getLogger("flydesk.search")


def _cache_key(criteria: SearchCriteria) -> str:
    digest = hashlib.sha1(criteria.model_dump_json().encode()).hexdigest()
    return f"offers:{digest}"


def cached_search(criteria: SearchCriteria) -> tuple[list[Offer], list[str], bool]:
    """Return (offers cheapest-first, degraded provider names, served_from_cache)."""
    key = _cache_key(criteria)

    try:
        hit = redis_client.get_redis().get(key)
    except redis.RedisError as exc:
        logger.warning("redis_unavailable_read error=%r", exc)
        hit = None

    if hit:
        offers = [Offer.model_validate(o) for o in json.loads(hit)]
        metrics.SEARCHES.labels(cached="true").inc()
        return offers, [], True

    offers, degraded = async_to_sync(search_all)(criteria, get_async_providers())
    metrics.SEARCHES.labels(cached="false").inc()
    for provider_name in degraded:
        metrics.PROVIDER_DEGRADED.labels(provider=provider_name).inc()

    if not degraded:
        try:
            redis_client.get_redis().set(
                key,
                json.dumps([o.model_dump(mode="json") for o in offers]),
                ex=get_settings().offer_cache_ttl,
            )
        except redis.RedisError as exc:
            logger.warning("redis_unavailable_write error=%r", exc)

    return offers, degraded, False
