"""Worker process: consume BookingConfirmed and run all three consumers.

Run as its own process:  python manage.py consume_events

At-least-once: we commit the offset only AFTER processing succeeds, and every
consumer is idempotent (dedupe on event id), so redelivery is safe.
"""

import asyncio
import json

from django.core.management.base import BaseCommand

from flydesk.bookings.repository import OrderRepository
from flydesk.common.config import get_settings
from flydesk.common.mongo import get_db
from flydesk.events.consumers import handle_audit, handle_notification, handle_ticketing
from flydesk.events.dedupe import ProcessedEvents
from flydesk.events.publisher import KafkaEventPublisher
from flydesk.events.topics import BOOKINGS_CONFIRMED


class Command(BaseCommand):
    help = "Consume BookingConfirmed and run ticketing/notifications/audit consumers."

    def handle(self, *args, **options):
        asyncio.run(self._run())

    async def _run(self):
        from aiokafka import AIOKafkaConsumer
        from prometheus_client import start_http_server

        start_http_server(8001)  # Prometheus scrapes this process's metrics here
        settings = get_settings()
        consumer = AIOKafkaConsumer(
            BOOKINGS_CONFIRMED,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="flydesk-workers",
            enable_auto_commit=False,  # commit AFTER processing -> at-least-once
            auto_offset_reset="earliest",
            value_deserializer=lambda b: json.loads(b.decode()),
        )
        publisher = KafkaEventPublisher(settings.kafka_bootstrap_servers)
        await consumer.start()
        await publisher.start()

        repo = OrderRepository()
        dedupe = ProcessedEvents()
        audit = get_db()["audit_log"]
        self.stdout.write(f"consuming {BOOKINGS_CONFIRMED} ...")
        try:
            async for message in consumer:
                event = message.value
                await handle_ticketing(event, repository=repo, dedupe=dedupe, publisher=publisher)
                await handle_notification(event, dedupe=dedupe)
                await handle_audit(event, dedupe=dedupe, audit_collection=audit)
                await consumer.commit()
        finally:
            await consumer.stop()
            await publisher.stop()
