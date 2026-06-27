"""Cache-aside on search: miss populates Redis, second call is served from cache."""

from datetime import date

from flydesk.domain import SearchCriteria
from flydesk.providers.duffel import mapper, schemas
from flydesk.providers.mock import MockProvider
from flydesk.search import cache


def _offers(load):
    parsed = schemas.DuffelOfferRequestResponse.model_validate(
        load("duffel", "offer_request_response.json")
    )
    return [mapper.map_offer(o) for o in parsed.data.offers]


def test_miss_then_hit(load, monkeypatch, fake_redis):
    offers = _offers(load)

    calls = {"n": 0}

    def providers():
        calls["n"] += 1
        return [MockProvider("duffel", offers)]

    monkeypatch.setattr(cache, "get_async_providers", providers)
    criteria = SearchCriteria(origin="LHR", destination="JFK", departure_date=date(2026, 8, 15))

    first, degraded, cached = cache.cached_search(criteria)
    assert cached is False and degraded == [] and len(first) == len(offers)

    second, _, cached2 = cache.cached_search(criteria)
    assert cached2 is True
    assert [o.id for o in second] == [o.id for o in first]
    assert calls["n"] == 1  # providers fanned out only once; the rest came from Redis


def test_degraded_results_are_not_cached(load, monkeypatch, fake_redis):
    offers = _offers(load)

    def providers():
        # one healthy, one broken -> degraded -> must NOT be cached
        from flydesk.common.exceptions import ProviderError

        return [MockProvider("duffel", offers), MockProvider("broken", [], fail=ProviderError("x"))]

    monkeypatch.setattr(cache, "get_async_providers", providers)
    criteria = SearchCriteria(origin="LHR", destination="JFK", departure_date=date(2026, 8, 15))

    _, degraded, cached = cache.cached_search(criteria)
    assert degraded == ["broken"] and cached is False
    # nothing cached -> next call still a miss
    _, _, cached2 = cache.cached_search(criteria)
    assert cached2 is False
