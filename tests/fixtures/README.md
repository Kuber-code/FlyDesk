# Provider payload fixtures — your Pydantic practice ground

These are realistic (sandbox-shaped) responses from the two providers. They are
the raw input to the **anti-corruption layer** (`flydesk/providers/*/schemas.py`
+ `mapper.py`), which turns them into the single normalized `Offer`/`Order`
domain model. Map both, get the same shape out — that's the whole exercise.

## Files

| File | Endpoint it represents | Use it to practice |
|---|---|---|
| `duffel/offer_request_response.json` | `POST /air/offer_requests?return_offers=true` | parsing a list of offers; a 1-stop connection vs a direct flight |
| `duffel/offer_get_response.json` | `GET /air/offers/{id}` | the re-price/revalidate step before booking |
| `duffel/order_create_response.json` | `POST /air/orders` | reading back the PNR (`booking_reference`) |
| `amadeus/flight_offers_search_response.json` | `GET/POST /v2/shopping/flight-offers` | a totally different shape: `dictionaries`, camelCase, round trip |
| `amadeus/flight_offers_price_response.json` | `POST /v1/shopping/flight-offers/pricing` | note the price moved 1054.70 → 1078.30 (offers are perishable!) |
| `amadeus/flight_create_orders_response.json` | `POST /v1/booking/flight-orders` | PNR in `associatedRecords[].reference` |

## The two shapes are deliberately different

| Concern | Duffel | Amadeus |
|---|---|---|
| Casing | `snake_case` | `camelCase` |
| Carrier/aircraft names | inline on each segment | only codes; names in a top-level `dictionaries` block |
| Cabin class | `segment.passengers[].cabin_class` | `travelerPricings[].fareDetailsBySegment[].cabin` |
| A journey leg | `slice` (has its own `id`) | `itinerary` (no id — we synthesize one) |
| Money | `total_amount` + `total_currency` strings | `price.grandTotal` + `price.currency` |
| Validity | `expires_at` on the offer | `lastTicketingDate` (modelled, not mapped to `expires_at`) |

If your mapper can flatten *both* of these into the same `Offer`, you understand
why the anti-corruption layer exists (interview Q8, Q25, Q26, Q38).

## Exercises (increasing difficulty)

1. **Parse strictly.** Load `duffel/offer_request_response.json`, validate it with
   `DuffelOfferRequestResponse.model_validate(...)`, and print `offers[0].id`.
2. **Break it on purpose.** Change `total_amount` to `"not-a-number"` and watch
   Pydantic fail *at the edge* with a precise error (that's the point).
3. **Normalize.** Map both providers' search payloads to `list[Offer]` and assert
   the Amadeus round trip yields 2 slices, the Duffel connection yields `stops == 1`.
4. **Serialize safely.** `offer.model_dump(mode="json")` and confirm money is a
   string (`"412.40"`), never a float.
5. **Round-trip a domain object.** `Order` -> `model_dump(mode="json")` ->
   store -> `Order.model_validate(...)` and assert equality (this is exactly what
   the Mongo repository does).

Run the reference solutions: `pytest tests/test_duffel_mapper.py tests/test_amadeus_mapper.py -v`
