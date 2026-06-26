"""
Capture live Duffel sandbox responses into fixture files ("record cassettes").

Usage:
    python scripts/capture_duffel.py [output_dir]

Reads DUFFEL_API_TOKEN from .env and runs the full shop -> price -> book flow
against the Duffel **test** API, saving each raw response as JSON. Re-run this to
refresh the fixtures whenever you want them grounded in a real response.
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TOKEN = os.environ.get("DUFFEL_API_TOKEN", "")
BASE = os.environ.get("DUFFEL_API_URL", "https://api.duffel.com").rstrip("/")
VERSION = os.environ.get("DUFFEL_API_VERSION", "v2")

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "fixtures" / "duffel"
OUT.mkdir(parents=True, exist_ok=True)

if not TOKEN.startswith("duffel_test_"):
    sys.exit("Refusing to run without a duffel_test_ token in .env")

client = httpx.Client(
    base_url=BASE,
    timeout=60.0,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Duffel-Version": VERSION,
        "Accept": "application/json",
        "Content-Type": "application/json",
    },
)


def save(name: str, payload: dict) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"   saved {path}  ({path.stat().st_size:,} bytes)")


def main() -> None:
    departure = (date.today() + timedelta(days=49)).isoformat()
    print(f"1) POST /air/offer_requests  LHR->JFK {departure}  1 adult economy")
    body = {
        "data": {
            "slices": [{"origin": "LHR", "destination": "JFK", "departure_date": departure}],
            "passengers": [{"type": "adult"}],
            "cabin_class": "economy",
        }
    }
    r = client.post("/air/offer_requests?return_offers=true&supplier_timeout=20000", json=body)
    r.raise_for_status()
    offer_req = r.json()
    offers = offer_req["data"]["offers"]
    print(f"   -> {len(offers)} offers")
    save("offer_request_response.json", offer_req)

    chosen = sorted(offers, key=lambda o: float(o["total_amount"]))[0]
    print(f"2) GET /air/offers/{chosen['id']}  (re-price)")
    r = client.get(f"/air/offers/{chosen['id']}")
    r.raise_for_status()
    offer_get = r.json()
    save("offer_get_response.json", offer_get)
    offer = offer_get["data"]

    passengers = [
        {
            "id": p["id"],
            "title": "mr",
            "gender": "m",
            "given_name": "Tony",
            "family_name": "Stark",
            "born_on": "1980-07-24",
            "email": "tony@example.com",
            "phone_number": "+442080160508",
        }
        for p in offer["passengers"]
    ]
    order_body = {
        "data": {
            "type": "instant",
            "selected_offers": [offer["id"]],
            "payments": [
                {
                    "type": "balance",
                    "currency": offer["total_currency"],
                    "amount": offer["total_amount"],
                }
            ],
            "passengers": passengers,
        }
    }
    print("3) POST /air/orders  (book)")
    r = client.post("/air/orders", json=order_body)
    if r.status_code >= 400:
        print(f"   !! order failed {r.status_code}")
        save("order_create_error.json", r.json())
        print(json.dumps(r.json(), indent=2)[:1500])
        return
    order = r.json()
    print(f"   -> booked, PNR {order['data'].get('booking_reference')}")
    save("order_create_response.json", order)


if __name__ == "__main__":
    main()
