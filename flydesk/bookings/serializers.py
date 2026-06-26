"""DRF validation for the booking request. Domain/PII rules live in the Pydantic
`BookingPassenger` in the service layer."""

from rest_framework import serializers

PASSENGER_CHOICES = ["adult", "child", "infant_without_seat"]


class BookingPassengerSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=PASSENGER_CHOICES, default="adult")
    title = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    given_name = serializers.CharField()
    family_name = serializers.CharField()
    born_on = serializers.DateField()
    email = serializers.EmailField()
    phone_number = serializers.CharField()


class CreateBookingSerializer(serializers.Serializer):
    offer_id = serializers.CharField()
    passengers = BookingPassengerSerializer(many=True, min_length=1)
