"""Root URL configuration for FlyDesk."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(_request):
    """Liveness probe — used by docker-compose/Coolify health checks."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("api/v1/", include("flydesk.search.urls")),
    path("api/v1/", include("flydesk.bookings.urls")),
]
