"""Domain model behaviour: validators, coercion, computed fields, serialization."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from flydesk.domain import Carrier, Money, Place, SearchCriteria
from flydesk.domain.enums import CabinClass


def test_money_normalizes_currency_and_serializes_as_string():
    money = Money(amount=Decimal("412.4"), currency="gbp")
    dumped = money.model_dump(mode="json")
    assert dumped == {"amount": "412.40", "currency": "GBP"}


def test_iata_codes_are_validated_and_uppercased():
    assert Place(iata_code="lhr").iata_code == "LHR"
    assert Carrier(iata_code="ba").iata_code == "BA"

    with pytest.raises(ValidationError):
        Place(iata_code="LON1")  # 4 chars
    with pytest.raises(ValidationError):
        Carrier(iata_code="BAA")  # carrier code is 2 chars


def test_search_criteria_rejects_same_origin_destination():
    with pytest.raises(ValidationError):
        SearchCriteria(origin="LHR", destination="LHR", departure_date=date(2026, 8, 15))


def test_search_criteria_rejects_return_before_departure():
    with pytest.raises(ValidationError):
        SearchCriteria(
            origin="LHR",
            destination="JFK",
            departure_date=date(2026, 8, 15),
            return_date=date(2026, 8, 10),
        )


def test_search_criteria_defaults_one_adult_economy():
    criteria = SearchCriteria(origin="lhr", destination="jfk", departure_date=date(2026, 8, 15))
    assert criteria.origin == "LHR"
    assert criteria.cabin_class is CabinClass.ECONOMY
    assert len(criteria.passengers) == 1
    assert criteria.is_round_trip is False
