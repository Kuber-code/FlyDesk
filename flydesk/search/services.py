"""Search service helpers. The async fan-out itself lives in `async_service.py`."""

from flydesk.domain import PassengerSpec, SearchCriteria


def build_criteria(data: dict) -> SearchCriteria:
    """Validated request dict -> domain SearchCriteria.

    SearchCriteria applies the domain invariants (origin != destination,
    return >= departure, IATA format) and raises on violation; the DRF exception
    handler turns that into a 400.
    """
    passengers = [PassengerSpec(**p) for p in (data.get("passengers") or [{}])]
    return SearchCriteria(
        origin=data["origin"],
        destination=data["destination"],
        departure_date=data["departure_date"],
        return_date=data.get("return_date"),
        cabin_class=data.get("cabin_class", "economy"),
        passengers=passengers,
        max_connections=data.get("max_connections", 1),
    )
