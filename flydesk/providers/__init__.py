"""Provider abstraction + concrete providers (Duffel live, Amadeus stub)."""

from flydesk.providers.base import FlightProvider, get_provider

__all__ = ["FlightProvider", "get_provider"]
