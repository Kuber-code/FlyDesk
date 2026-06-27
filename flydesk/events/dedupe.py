"""
Consumer idempotency (interview Q21/Q31).

We design for **at-least-once + idempotent consumers**: each consumer records
`(consumer, event_id)` the first time it sees an event; a duplicate insert means
"already processed", so redelivery is a no-op. A unique index makes that atomic.
"""

from datetime import UTC, datetime

from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from flydesk.common.mongo import get_db


class ProcessedEvents:
    def __init__(self, collection: Collection | None = None):
        self._col = collection if collection is not None else get_db()["processed_events"]
        self._col.create_index(
            [("consumer", 1), ("event_id", 1)], unique=True, name="uniq_consumer_event"
        )

    def mark_if_new(self, event_id: str, *, consumer: str) -> bool:
        """True if this is the first time `consumer` sees `event_id`."""
        try:
            self._col.insert_one(
                {"consumer": consumer, "event_id": event_id, "at": datetime.now(UTC)}
            )
            return True
        except DuplicateKeyError:
            return False
