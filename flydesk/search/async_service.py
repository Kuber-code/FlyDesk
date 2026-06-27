"""
Async fan-out search (Phase 2).

This is the interview-favourite shape made real (Q1/Q2/Q4/Q32):
- fan out to every provider **concurrently** with `asyncio.gather`,
- bound concurrency with a **`Semaphore`** (protect pools / downstreams),
- put a **per-provider deadline** on each call with `asyncio.timeout`,
- **degrade gracefully**: `return_exceptions=True` so one slow/failing provider
  can't sink the whole search — we return what the healthy ones gave us and
  report which providers degraded.

Total latency is ~the slowest *healthy* provider, not the sum.
"""

import asyncio
import logging

from flydesk.common.exceptions import ProviderError
from flydesk.common.resilience import get_breaker, retry_async
from flydesk.domain import Offer, SearchCriteria
from flydesk.providers.base import AsyncFlightProvider

logger = logging.getLogger("flydesk.search")


async def search_all(
    criteria: SearchCriteria,
    providers: list[AsyncFlightProvider],
    *,
    per_provider_timeout: float = 8.0,
    max_concurrency: int = 10,
) -> tuple[list[Offer], list[str]]:
    """Return (aggregated offers cheapest-first, names of degraded providers)."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _search_one(provider: AsyncFlightProvider) -> list[Offer]:
        breaker = get_breaker(str(provider.name))

        async def _attempt() -> list[Offer]:
            async with asyncio.timeout(per_provider_timeout):
                return await provider.search(criteria)

        async with semaphore:
            # breaker(retry(timeout(call))): retry transient blips, trip the
            # breaker only on persistent failure so we fail fast next time.
            return await breaker.call(
                retry_async, _attempt, attempts=2, retry_on=(ProviderError, TimeoutError)
            )

    results = await asyncio.gather(*(_search_one(p) for p in providers), return_exceptions=True)

    offers: list[Offer] = []
    degraded: list[str] = []
    for provider, result in zip(providers, results, strict=True):
        name = str(getattr(provider, "name", provider))
        if isinstance(result, Exception):
            degraded.append(name)
            logger.warning("search_provider_degraded provider=%s error=%r", name, result)
        else:
            offers.extend(result)

    offers.sort(key=lambda o: o.total.amount)
    logger.info(
        "search_fanout offers=%d providers=%d degraded=%d",
        len(offers),
        len(providers),
        len(degraded),
    )
    return offers, degraded
