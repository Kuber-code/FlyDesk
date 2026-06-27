"""Outbox relay process: poll Mongo for unpublished events, publish to Kafka.

Run as its own process:  python manage.py relay_outbox
"""

import asyncio

from django.core.management.base import BaseCommand

from flydesk.common.config import get_settings
from flydesk.events.publisher import KafkaEventPublisher
from flydesk.events.relay import relay_once


class Command(BaseCommand):
    help = "Publish pending outbox events to Kafka (transactional outbox relay)."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=2.0)
        parser.add_argument("--once", action="store_true", help="Relay once and exit.")

    def handle(self, *args, **options):
        asyncio.run(self._run(options["interval"], options["once"]))

    async def _run(self, interval: float, once: bool):
        publisher = KafkaEventPublisher(get_settings().kafka_bootstrap_servers)
        await publisher.start()
        self.stdout.write("outbox relay started")
        try:
            while True:
                published = await relay_once(publisher)
                if published:
                    self.stdout.write(f"relayed {published} event(s)")
                if once:
                    break
                await asyncio.sleep(interval)
        finally:
            await publisher.stop()
