"""
MockProvider — an in-memory async provider for fan-out and resilience tests.

Lets us prove the things that matter in Phase 2 without real network: results
aggregate across providers, a slow provider trips its timeout, and a failing
provider degrades gracefully instead of taking the whole search down.
"""

import asyncio

from flydesk.domain import Offer, SearchCriteria
from flydesk.providers.base import AsyncFlightProvider


class MockProvider(AsyncFlightProvider):
    def __init__(
        self,
        name: str,
        offers: list[Offer],
        *,
        delay: float = 0.0,
        fail: Exception | None = None,
    ):
        self.name = name
        self._offers = offers
        self._delay = delay
        self._fail = fail

    async def search(self, criteria: SearchCriteria) -> list[Offer]:
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._fail is not None:
            raise self._fail
        return list(self._offers)
