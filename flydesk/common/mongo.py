"""
MongoDB access (Phase 1: sync pymongo).

Domain documents (orders) are persisted here through a repository layer, not the
Django ORM. Phase 2/3 may swap pymongo for `motor` on async paths; keeping all
Mongo access behind these accessors makes that swap local.
"""

from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from flydesk.common.config import get_settings


@lru_cache
def get_client() -> MongoClient:
    settings = get_settings()
    # tz_aware so datetimes come back as timezone-aware UTC, matching our models.
    return MongoClient(settings.mongo_uri, tz_aware=True)


def get_db() -> Database:
    return get_client()[get_settings().mongo_db]


def orders_collection() -> Collection:
    return get_db()["orders"]
