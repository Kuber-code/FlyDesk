"""POST /api/v1/search — thin HTTP layer over the search service."""

from rest_framework.response import Response
from rest_framework.views import APIView

from flydesk.search.serializers import SearchRequestSerializer
from flydesk.search.services import search_offers


class SearchView(APIView):
    def post(self, request):
        serializer = SearchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        offers = search_offers(serializer.validated_data)
        return Response({"count": len(offers), "offers": offers})
