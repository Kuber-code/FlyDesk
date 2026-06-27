"""Circuit breaker + retry primitives."""

import pytest

from flydesk.common.resilience import CircuitBreaker, CircuitOpenError, retry_async


async def test_breaker_opens_after_threshold_then_fails_fast():
    breaker = CircuitBreaker(name="t", failure_threshold=2, reset_timeout=60.0)

    async def boom():
        raise ValueError("nope")

    for _ in range(2):
        with pytest.raises(ValueError):
            await breaker.call(boom)

    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError):  # fails fast, doesn't call boom()
        await breaker.call(boom)


async def test_breaker_half_opens_and_closes_on_success():
    breaker = CircuitBreaker(name="t", failure_threshold=1, reset_timeout=0.05)

    async def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await breaker.call(boom)
    assert breaker.state == "open"

    import asyncio

    await asyncio.sleep(0.06)  # let the cooldown elapse
    assert breaker.state == "half_open"

    async def ok():
        return 42

    assert await breaker.call(ok) == 42
    assert breaker.state == "closed"


async def test_retry_succeeds_after_transient_failures():
    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TimeoutError("transient")
        return "ok"

    result = await retry_async(flaky, attempts=5, base_delay=0.001, retry_on=(TimeoutError,))
    assert result == "ok"
    assert attempts["n"] == 3


async def test_retry_gives_up_and_raises_last():
    async def always_fails():
        raise TimeoutError("still down")

    with pytest.raises(TimeoutError):
        await retry_async(always_fails, attempts=3, base_delay=0.001, retry_on=(TimeoutError,))
