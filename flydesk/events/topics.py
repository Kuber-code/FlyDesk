"""Topic names + event-type → topic routing."""

BOOKINGS_CONFIRMED = "bookings.confirmed"
TICKETS_ISSUED = "tickets.issued"

TOPIC_FOR_EVENT = {
    "BookingConfirmed": BOOKINGS_CONFIRMED,
    "TicketIssued": TICKETS_ISSUED,
}


def topic_for(event_type: str) -> str:
    return TOPIC_FOR_EVENT.get(event_type, "events.dead_letter")
