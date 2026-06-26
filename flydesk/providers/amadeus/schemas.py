"""
Pydantic models of Amadeus's *raw* Flight Offers Search payload.

Amadeus uses camelCase and pushes carrier/aircraft names into a `dictionaries`
block keyed by code — a different shape from Duffel, which is exactly why the
anti-corruption layer earns its keep: two messy vocabularies, one clean domain.

Reference: Amadeus Self-Service — Flight Offers Search / Price / Create Orders.
(Modelled, not called live: the Self-Service portal retires mid-2026 — Q42.)
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Raw(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class AmadeusEndpoint(_Raw):
    iata_code: str = Field(alias="iataCode")
    terminal: str | None = None
    at: datetime


class AmadeusAircraft(_Raw):
    code: str | None = None


class AmadeusOperating(_Raw):
    carrier_code: str | None = Field(default=None, alias="carrierCode")


class AmadeusSegment(_Raw):
    id: str
    departure: AmadeusEndpoint
    arrival: AmadeusEndpoint
    carrier_code: str = Field(alias="carrierCode")
    number: str
    aircraft: AmadeusAircraft | None = None
    operating: AmadeusOperating | None = None
    duration: str | None = None
    number_of_stops: int = Field(default=0, alias="numberOfStops")


class AmadeusItinerary(_Raw):
    duration: str | None = None
    segments: list[AmadeusSegment]


class AmadeusFee(_Raw):
    amount: Decimal
    type: str


class AmadeusPrice(_Raw):
    currency: str
    total: Decimal
    base: Decimal | None = None
    grand_total: Decimal | None = Field(default=None, alias="grandTotal")
    fees: list[AmadeusFee] = Field(default_factory=list)


class AmadeusFareDetail(_Raw):
    segment_id: str = Field(alias="segmentId")
    cabin: str | None = None
    fare_basis: str | None = Field(default=None, alias="fareBasis")
    booking_class: str | None = Field(default=None, alias="class")


class AmadeusTravelerPricing(_Raw):
    traveler_id: str = Field(alias="travelerId")
    traveler_type: str = Field(alias="travelerType")
    fare_details_by_segment: list[AmadeusFareDetail] = Field(
        default_factory=list, alias="fareDetailsBySegment"
    )


class AmadeusFlightOffer(_Raw):
    id: str
    source: str | None = None
    itineraries: list[AmadeusItinerary]
    price: AmadeusPrice
    validating_airline_codes: list[str] = Field(
        default_factory=list, alias="validatingAirlineCodes"
    )
    traveler_pricings: list[AmadeusTravelerPricing] = Field(
        default_factory=list, alias="travelerPricings"
    )


class AmadeusDictionaries(_Raw):
    carriers: dict[str, str] = Field(default_factory=dict)
    aircraft: dict[str, str] = Field(default_factory=dict)
    locations: dict[str, Any] = Field(default_factory=dict)


class AmadeusFlightOffersResponse(_Raw):
    data: list[AmadeusFlightOffer]
    dictionaries: AmadeusDictionaries | None = None
