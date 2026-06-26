from django.urls import path

from flydesk.bookings.views import BookingDetailView, BookingsView

urlpatterns = [
    path("bookings", BookingsView.as_view(), name="bookings"),
    path("bookings/<str:order_id>", BookingDetailView.as_view(), name="booking-detail"),
]
