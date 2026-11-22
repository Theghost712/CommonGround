"""Serve the built React app (index.html) for every non-API path.

Used when one service hosts both the API and the website (e.g. Render's free tier).
The app shell is never cached, so a new deploy shows up at once, and it carries the
same Content-Security-Policy as deploy/nginx.conf.
"""
from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET


def content_security_policy():
    media = " ".join(["'self'", "blob:", *settings.CSP_MEDIA_ORIGINS])
    images = " ".join(["'self'", "data:", "blob:", "https:"])
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        f"img-src {images}",
        f"media-src {media}",
        "connect-src 'self'",  # same-origin API and WebSockets (wss: included by 'self')
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ])


@require_GET
def spa_index(request):
    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise Http404("Frontend build not found.")
    response = HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["Content-Security-Policy"] = content_security_policy()
    response["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(), payment=()"
    return response
