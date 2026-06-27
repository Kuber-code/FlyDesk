"""
Resilience primitives for outbound provider calls (interview Q5/Q32):

- `retry_async` — bounded retries with exponential backoff + jitter, for
  *transient* failures only (timeouts, 5xx). Never used on non-idempotent writes.
- `CircuitBreaker` — stop hammering a provider that's failing: after N failures
  the circuit OPENS and calls fail fast; after a cooldown it goes HALF-OPEN to
  probe; a success CLOSES it again.

A process-level registry keeps one breaker per provider so state persists across
requests.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger("flydesk.resilience")


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""


async def retry_async[T](
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 2,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return await func()
        except retry_on as exc:
            last_exc = exc
            if i == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2**i)) * (0.5 + random.random())
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


class CircuitBreaker:
    def __init__(
        self, *, name: str = "cb", failure_threshold: int = 3, reset_timeout: float = 30.0
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if (time.monotonic() - self._opened_at) >= self.reset_timeout:
            return "half_open"
        return "open"

    def _on_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def _on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()

    async def call[T](self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        if self.state == "open":
            raise CircuitOpenError(f"circuit '{self.name}' is open")
        try:
            result = await func(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise
        self._on_success()
        return result


_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str) -> CircuitBreaker:
    return _breakers.setdefault(name, CircuitBreaker(name=name))


def reset_breakers() -> None:
    """Clear all breaker state (used between tests)."""
    _breakers.clear()
