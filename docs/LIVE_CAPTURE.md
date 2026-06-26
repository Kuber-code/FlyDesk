# Grounding the Duffel fixtures in live data

The `tests/fixtures/duffel/*.json` files are **real captures** from the Duffel
sandbox, not hand-written shapes. Here's how they were produced and what changed.

## Method (how it was done)

1. Put the `duffel_test_` token in `.env` (git-ignored).
2. [`scripts/capture_duffel.py`](../scripts/capture_duffel.py) runs the real
   **shop → price → book** flow against `api.duffel.com` and saves three raw
   responses: the offer request (search), a single offer (re-price), and the
   created order.
3. Ran every captured payload through the **existing** Pydantic schemas + mappers
   (the anti-corruption layer) to confirm it parses.
4. Trimmed the search response from 258 offers to 3 representative real ones (a
   direct, a connection, and a second carrier) and installed all three as fixtures.
5. Updated the Duffel tests to assert the real captured values. Suite stays green.

Refresh anytime with: `python scripts/capture_duffel.py`

## Headline result

**The ACL parsed all 258 live offers AND the live order with zero code changes.**
`extra="ignore"` on the raw schemas absorbed everything Duffel returns beyond what
we map. That's the anti-corruption layer proven against reality, not just against
my own hand-written JSON.

## What differed: synthetic guess → live truth

| | My synthetic fixture | Live Duffel sandbox |
|---|---|---|
| Offers per search | 2 | **258** (15 carriers: AA, BA, EI, LH, LO, TP, IB…) |
| Currency (LHR–JFK) | GBP (guessed) | **USD** |
| Prices | invented (412.40) | real (AA 217.02, IB 223.87, TP 611.73) |
| Offer / order IDs | placeholders | real (`off_0000B7jt…`, `ord_0000B7jt…`) |
| PNR | `RZ2PML` (made up) | **`345FKK`** (real sandbox PNR) |
| Aircraft | always present | can be **`null`** (the AA segment had none) |

**Extra fields Duffel sends that we (correctly) ignore:**
- *Offer* (18): `conditions`, `payment_requirements`, `total_emissions_kg`,
  `passenger_identity_documents_required`, `available_services`, `private_fares`,
  `created_at`/`updated_at`, `live_mode`, `partial`, `base_currency`,
  `supported_loyalty_programmes`, …
- *Segment* (5): `origin_terminal`, `destination_terminal`,
  `operating_carrier_flight_number`, `distance`, `stops` (intra-segment tech stops).
- *Order* (24): `documents` (the e-ticket), `cancellation`, `void_window_ends_at`,
  `payment_status`, `available_actions`, `owner`, `metadata`, `offer_id`,
  `booking_references`, …
- *Places* carry `icao_code`, `latitude`/`longitude`, `time_zone`, and a nested
  `city` — all ignored; we keep just IATA code + names.

## A real bug the live API surfaced

Duffel **requires `gender` (`"m"`/`"f"`) on order passengers.** My doc-based
`create_order` sent `title` but not `gender`, so a real booking would have failed.
Fix: `gender` added to `BookingPassenger`, the booking serializer, and the Duffel
order payload. This is exactly why you validate a doc-derived model against a live
sandbox — and it's good interview material ("modelled from docs, then reconciled
against a real capture").
