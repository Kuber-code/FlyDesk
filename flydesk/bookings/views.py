"""POST /api/v1/bookings and GET /api/v1/bookings/{id} — thin HTTP layer."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from flydesk.bookings.serializers import CreateBookingSerializer
from flydesk.bookings.services import create_booking, get_booking


class BookingsView(APIView):
    def post(self, request):
        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_booking(
            offer_id=serializer.validated_data["offer_id"],
            passengers_data=serializer.validated_data["passengers"],
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
        return Response(order.model_dump(mode="json"), status=status.HTTP_201_CREATED)


class BookingDetailView(APIView):
    def get(self, request, order_id: str):
        order = get_booking(order_id)
        return Response(order.model_dump(mode="json"))
