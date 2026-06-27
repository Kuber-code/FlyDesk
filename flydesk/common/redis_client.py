"""Sync Redis accessor. Used for the offer cache and idempotency reservation.

We use the sync client at the (sync) view/service boundary; the async fan-out
sits underneath via async_to_sync. Call sites go through `redis_client.get_redis()`
(module attribute) so tests can swap in fakeredis with one monkeypatch.
"""

from functools import lru_cache

import redis

from flydesk.common.config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
