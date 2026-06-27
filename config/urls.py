"""Root URL configuration for FlyDesk."""

from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def healthz(_request):
    """Liveness probe — used by docker-compose/Coolify health checks."""
    return JsonResponse({"status": "ok"})


def metrics(_request):
    """Prometheus scrape endpoint."""
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("metrics", metrics, name="metrics"),
    path("api/v1/", include("flydesk.search.urls")),
    path("api/v1/", include("flydesk.bookings.urls")),
]
