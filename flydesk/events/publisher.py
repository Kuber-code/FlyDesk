"""
Event publisher port + implementations.

The port keeps the relay/consumers ignorant of Kafka — tests use the in-memory
publisher, production uses Kafka (aiokafka). aiokafka is imported lazily so the
core app and the test suite don't need the broker library installed.
"""

import json
from abc import ABC, abstractmethod


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, topic: str, key: str, value: dict) -> None: ...


class InMemoryEventPublisher(EventPublisher):
    """Collects published messages — for tests and local dry-runs."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str, dict]] = []

    async def publish(self, topic: str, key: str, value: dict) -> None:
        self.published.append((topic, key, value))


class KafkaEventPublisher(EventPublisher):
    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap = bootstrap_servers
        self._producer = None

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer  # lazy: only needed to run live

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if k is not None else None,
            enable_idempotence=True,  # no duplicate producer records on retry
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()

    async def publish(self, topic: str, key: str, value: dict) -> None:
        assert self._producer is not None, "call start() first"
        # Key by entity id so all events for one booking land on one partition,
        # preserving per-booking ordering (interview Q22).
        await self._producer.send_and_wait(topic, value=value, key=key)
