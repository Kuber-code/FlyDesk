"""Shared pytest fixtures: fixture loader + an in-memory Mongo (mongomock)."""

import json
from pathlib import Path

import mongomock
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(*parts: str) -> dict:
    return json.loads(FIXTURES_DIR.joinpath(*parts).read_text(encoding="utf-8"))


@pytest.fixture
def load():
    """Return the fixture loader, e.g. load('duffel', 'offer_get_response.json')."""
    return load_fixture


@pytest.fixture
def mongo_collection():
    client = mongomock.MongoClient()
    return client["flydesk_test"]["orders"]


@pytest.fixture(autouse=True)
def _patch_mongo(monkeypatch, mongo_collection):
    """Point the repository at the in-memory collection for every test."""
    from flydesk.bookings import repository

    monkeypatch.setattr(repository, "orders_collection", lambda: mongo_collection)
    repository.ensure_order_indexes.cache_clear()
    yield
    repository.ensure_order_indexes.cache_clear()


@pytest.fixture
def adult_passenger_payload():
    return {
        "type": "adult",
        "title": "mr",
        "gender": "m",
        "given_name": "Tony",
        "family_name": "Stark",
        "born_on": "1980-07-24",
        "email": "tony@starkindustries.com",
        "phone_number": "+442080160508",
    }
