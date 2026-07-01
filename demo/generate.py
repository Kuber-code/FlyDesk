"""
Deterministic offer generator for the demo.

The demo used to always load the same 3-offer fixture, so changing the route or
date showed identical results. This builds a **Duffel-shaped raw payload** from
the actual search criteria — varied carriers, prices, times, direct vs 1-stop —
seeded by (origin, destination, date) so the same query is stable but different
queries differ. Crucially it's still fed through the *real* Duffel schemas +
mapper (the anti-corruption layer), so the ACL story holds; only the input is
synthetic instead of a static file. No network, no token.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

CARRIERS = [
    ("BA", "British Airways"),
    ("AA", "American Airlines"),
    ("LH", "Lufthansa"),
    ("AF", "Air France"),
    ("KL", "KLM"),
    ("IB", "Iberia"),
    ("DL", "Delta Air Lines"),
    ("UA", "United Airlines"),
    ("VS", "Virgin Atlantic"),
    ("EI", "Aer Lingus"),
    ("TP", "TAP Air Portugal"),
    ("LO", "LOT Polish Airlines"),
]

AIRCRAFT = [
    "Airbus A320neo",
    "Boeing 737-800",
    "Boeing 787-9",
    "Airbus A350-900",
    "Boeing 777-300ER",
    None,  # Duffel sometimes returns null — exercise the optional path
]

HUBS = ["AMS", "CDG", "FRA", "IST", "MAD", "DUB", "LHR", "MUC", "ZRH", "CPH"]

# Rough currency by origin; anything else defaults to USD.
CURRENCY_BY_AIRPORT = {
    "LHR": "GBP",
    "LGW": "GBP",
    "MAN": "GBP",
    "EDI": "GBP",
    "WAW": "PLN",
    "KRK": "PLN",
    "GDN": "PLN",
    "CDG": "EUR",
    "FRA": "EUR",
    "AMS": "EUR",
    "MAD": "EUR",
    "MUC": "EUR",
    "BCN": "EUR",
    "FCO": "EUR",
    "LIS": "EUR",
    "DUB": "EUR",
}


def _iso_duration(minutes: int) -> str:
    return f"PT{minutes // 60}H{minutes % 60}M"


def _segment(
    seg_id: str,
    origin: str,
    destination: str,
    dep: datetime,
    minutes: int,
    carrier: tuple[str, str],
    cabin: str,
    rng: random.Random,
) -> dict:
    arr = dep + timedelta(minutes=minutes)
    aircraft = rng.choice(AIRCRAFT)
    return {
        "id": seg_id,
        "origin": {"iata_code": origin, "type": "airport"},
        "destination": {"iata_code": destination, "type": "airport"},
        "departing_at": dep.isoformat(),
        "arriving_at": arr.isoformat(),
        "marketing_carrier": {"iata_code": carrier[0], "name": carrier[1]},
        "operating_carrier": {"iata_code": carrier[0], "name": carrier[1]},
        "marketing_carrier_flight_number": str(rng.randint(100, 1999)),
        "aircraft": {"name": aircraft} if aircraft else None,
        "duration": _iso_duration(minutes),
        "passengers": [{"passenger_id": "pas_demo", "cabin_class": cabin}],
    }


def _offer(
    idx: int,
    origin: str,
    destination: str,
    dep_date: date,
    cabin: str,
    n_passengers: int,
    rng: random.Random,
) -> dict:
    carrier = rng.choice(CARRIERS)
    currency = CURRENCY_BY_AIRPORT.get(origin, "USD")
    direct = rng.random() < 0.55
    total_minutes = rng.randint(90, 620)
    dep_hour = rng.randint(6, 21)
    dep = datetime(
        dep_date.year, dep_date.month, dep_date.day, dep_hour, rng.choice([0, 15, 30, 45])
    )

    if direct:
        segments = [
            _segment(f"seg_{idx}_0", origin, destination, dep, total_minutes, carrier, cabin, rng)
        ]
    else:
        hub = rng.choice([h for h in HUBS if h not in (origin, destination)])
        leg1 = int(total_minutes * rng.uniform(0.4, 0.6))
        layover = rng.randint(45, 150)
        leg2 = max(60, total_minutes - leg1)
        seg1 = _segment(f"seg_{idx}_0", origin, hub, dep, leg1, carrier, cabin, rng)
        dep2 = dep + timedelta(minutes=leg1 + layover)
        seg2 = _segment(f"seg_{idx}_1", hub, destination, dep2, leg2, carrier, cabin, rng)
        segments = [seg1, seg2]

    # Price: base by duration + a carrier/random spread; connections a bit cheaper.
    base = 80 + total_minutes * rng.uniform(0.5, 1.1)
    if not direct:
        base *= 0.85
    total = round(base * n_passengers, 2)

    return {
        "id": f"off_demo_{origin}{destination}_{idx}_{rng.randint(1000, 9999)}",
        "owner": {"iata_code": carrier[0], "name": carrier[1]},
        "total_amount": f"{total:.2f}",
        "total_currency": currency,
        "slices": [
            {
                "id": f"sli_{idx}",
                "origin": {"iata_code": origin, "type": "airport"},
                "destination": {"iata_code": destination, "type": "airport"},
                "duration": _iso_duration(total_minutes),
                "segments": segments,
            }
        ],
        "passengers": [{"id": f"pas_{i}", "type": "adult"} for i in range(n_passengers)],
    }


def build_offer_request_payload(
    *,
    origin: str,
    destination: str,
    departure_date: date,
    cabin_class: str = "economy",
    n_passengers: int = 1,
    count: int | None = None,
) -> dict:
    """A Duffel `POST /air/offer_requests?return_offers=true`-shaped response,
    generated for the given route/date. Feed it to the real schemas + mapper."""
    seed = f"{origin}-{destination}-{departure_date.isoformat()}-{cabin_class}"
    rng = random.Random(seed)
    n = count if count is not None else rng.randint(9, 14)
    offers = [
        _offer(i, origin, destination, departure_date, cabin_class, n_passengers, rng)
        for i in range(n)
    ]
    return {"data": {"id": f"orq_demo_{abs(hash(seed)) % 10**8}", "offers": offers}}
