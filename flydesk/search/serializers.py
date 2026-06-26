"""
DRF serializers validate the *HTTP shape* of the request (required fields,
types, choices). Cross-field *domain* rules (origin != destination, return >=
departure, IATA format) live in the Pydantic `SearchCriteria` in the service
layer. Two layers, two jobs (interview Q8).
"""

from rest_framework import serializers

CABIN_CHOICES = ["economy", "premium_economy", "business", "first"]
PASSENGER_CHOICES = ["adult", "child", "infant_without_seat"]


class PassengerSpecSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=PASSENGER_CHOICES, default="adult")
    age = serializers.IntegerField(required=False, min_value=0, max_value=17)


class SearchRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(min_length=3, max_length=3)
    destination = serializers.CharField(min_length=3, max_length=3)
    departure_date = serializers.DateField()
    return_date = serializers.DateField(required=False, allow_null=True)
    cabin_class = serializers.ChoiceField(choices=CABIN_CHOICES, default="economy")
    passengers = PassengerSpecSerializer(many=True, required=False)
    max_connections = serializers.IntegerField(min_value=0, max_value=2, default=1)
