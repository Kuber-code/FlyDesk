"""
Order persistence in MongoDB (pymongo). The repository is the only thing that
knows the document shape, so the rest of the app stays in domain terms.

Modeling choice (interview Q11): an order embeds its slices/segments/passengers
and is read as ONE document — that's how it's accessed, so we embed rather than
normalize. Shared/dictionary data (airline, airport) stays as codes.
"""

from functools import lru_cache

from pymongo.collection import Collection

from flydesk.common.mongo import orders_collection
from flydesk.domain import Order


@lru_cache
def ensure_order_indexes() -> None:
    """Create indexes once per process. The unique index on idempotency_key is
    what actually prevents a duplicate booking under a race (interview Q31)."""
    col = orders_collection()
    col.create_index("idempotency_key", unique=True, sparse=True, name="uniq_idempotency_key")
    col.create_index("created_at", name="created_at")


class OrderRepository:
    def __init__(self, collection: Collection | None = None):
        self._col = collection if collection is not None else orders_collection()

    def save(self, order: Order) -> None:
        doc = order.model_dump(mode="json")
        doc["_id"] = doc.pop("id")
        self._col.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    def get(self, order_id: str) -> Order | None:
        doc = self._col.find_one({"_id": order_id})
        return self._to_order(doc) if doc else None

    def find_by_idempotency_key(self, key: str) -> Order | None:
        doc = self._col.find_one({"idempotency_key": key})
        return self._to_order(doc) if doc else None

    def find_with_unpublished_outbox(self, *, limit: int = 100) -> list[Order]:
        """Orders that have at least one outbox event awaiting publish.
        `$elemMatch` so an order with an all-published (or empty) outbox is excluded."""
        cursor = self._col.find({"outbox": {"$elemMatch": {"published_at": None}}}).limit(limit)
        return [self._to_order(doc) for doc in cursor]

    @staticmethod
    def _to_order(doc: dict) -> Order:
        doc = dict(doc)
        doc["id"] = doc.pop("_id")
        return Order.model_validate(doc)
