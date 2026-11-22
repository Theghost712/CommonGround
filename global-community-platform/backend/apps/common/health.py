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
