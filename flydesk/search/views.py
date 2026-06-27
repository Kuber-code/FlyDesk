"""POST /api/v1/search — fans out to providers concurrently (Phase 2).

The view stays a normal sync DRF view and drives the async fan-out via
`async_to_sync` (interview Q7). The concurrency itself — gather/semaphore/timeout
— lives in `async_service.search_all`. A fully-async ASGI handler is a later
refinement; the orchestration is already async and provider-agnostic.
"""

from asgiref.sync import async_to_sync
from rest_framework.response import Response
from rest_framework.views import APIView

from flydesk.providers.base import get_async_providers
from flydesk.search.async_service import search_all
from flydesk.search.serializers import SearchRequestSerializer
from flydesk.search.services import build_criteria


class SearchView(APIView):
    def post(self, request):
        serializer = SearchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        criteria = build_criteria(serializer.validated_data)  # raises -> 400 on bad domain input

        offers, degraded = async_to_sync(search_all)(criteria, get_async_providers())

        return Response(
            {
                "count": len(offers),
                "degraded_providers": degraded,
                "offers": [o.model_dump(mode="json") for o in offers],
            }
        )
