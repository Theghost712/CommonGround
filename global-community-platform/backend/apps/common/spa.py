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
        # Same-origin API and WebSockets, plus direct uploads to object storage.
        f"connect-src {' '.join(["'self'", *settings.CSP_MEDIA_ORIGINS])}",
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
    html = index.read_text(encoding="utf-8")
    from .seo import page_for_path, render_shell

    page = page_for_path(request.path)
    if page is not None:
        html = render_shell(html, page)
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["Content-Security-Policy"] = content_security_policy()
    response["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(), payment=()"
    return response
