"""GET /api/v1/health/: for load balancers and uptime monitors.

200 when the database and cache answer, 503 otherwise. No authentication, no rate
limit, no secrets in the response.
"""
import time

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def health(request):
    checks = {}
    started = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    try:
        cache.set("health:probe", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("health:probe") == "1" else "error"
    except Exception:
        checks["cache"] = "error"
    healthy = all(value == "ok" for value in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "error", "checks": checks, "ms": round((time.perf_counter() - started) * 1000, 1)},
        status=200 if healthy else 503,
    )


class HealthCheckMiddleware:
    """Answer /api/v1/health/ before host validation and HTTPS redirects.

    Platform health probes (Render, load balancers, Kubernetes) often call the
    container by its internal IP over plain HTTP. Django would reject that Host
    header with 400 (or redirect to https), the probe would fail, and the platform
    would mark a healthy deploy as failed. The response reveals nothing sensitive.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/api/v1/health/" and request.method == "GET":
            return health(request)
        return self.get_response(request)
