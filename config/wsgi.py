"""WSGI entry point for Phase 1 (sync). Served by gunicorn in production."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
