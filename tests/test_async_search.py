"""Phase 2: async fan-out search — aggregation, timeouts, graceful degradation."""

from datetime import date

import respx
from httpx import Response

from flydesk.common.exceptions import ProviderError
from flydesk.domain import SearchCriteria
from flydesk.providers.duffel import mapper, schemas
from flydesk.providers.duffel.async_client import AsyncDuffelProvider
from flydesk.providers.mock import MockProvider
from flydesk.search.async_service import search_all


def _offers(load):
    parsed = schemas.DuffelOfferRequestResponse.model_validate(
        load("duffel", "offer_request_response.json")
    )
    return [mapper.map_offer(o) for o in parsed.data.offers]


def _criteria():
    return SearchCriteria(origin="LHR", destination="JFK", departure_date=date(2026, 8, 15))


async def test_fanout_aggregates_and_sorts(load):
    offers = _offers(load)
    providers = [MockProvider("mock-a", offers[:1]), MockProvider("mock-b", offers[1:])]
    result, degraded = await search_all(_criteria(), providers)

    assert degraded == []
    assert len(result) == len(offers)
    amounts = [o.total.amount for o in result]
    assert amounts == sorted(amounts)  # merged, cheapest first


async def test_slow_provider_times_out_others_still_return(load):
    offers = _offers(load)
    providers = [
        MockProvider("healthy", offers),
        MockProvider("slow", offers, delay=0.5),
    ]
    result, degraded = await search_all(_criteria(), providers, per_provider_timeout=0.05)

    assert degraded == ["slow"]  # the slow one tripped its deadline
    assert len(result) == len(offers)  # the healthy one's offers came back


async def test_failing_provider_degrades_gracefully(load):
    offers = _offers(load)
    providers = [
        MockProvider("healthy", offers),
        MockProvider("broken", [], fail=ProviderError("boom")),
    ]
    result, degraded = await search_all(_criteria(), providers)

    assert degraded == ["broken"]
    assert len(result) == len(offers)


@respx.mock
async def test_async_duffel_search_parses_fixture(load):
    respx.route(method="POST", path="/air/offer_requests").mock(
        return_value=Response(200, json=load("duffel", "offer_request_response.json"))
    )
    provider = AsyncDuffelProvider(token="duffel_test_x", base_url="https://api.duffel.com")
    offers = await provider.search(_criteria())

    assert len(offers) == 3
    amounts = [o.total.amount for o in offers]
    assert amounts == sorted(amounts)
