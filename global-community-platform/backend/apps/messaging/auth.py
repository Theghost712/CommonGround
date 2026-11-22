import hashlib
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache

User = get_user_model()
logger = logging.getLogger(__name__)


def consume_cached_ticket(key):
    payload = cache.get(key)
    if not isinstance(payload, dict) or not payload.get("id"):
        return None
    if not cache.add(
        f"{key}:used", True, timeout=settings.WEBSOCKET_TICKET_TTL_SECONDS + 5
    ):
        return None
    cache.delete(key)
    return payload


def _consume_ticket_and_get_active_user(key):
    payload = consume_cached_ticket(key)
    if payload is None:
        return None
    try:
        return User.objects.get(pk=payload["id"], is_active=True)
    except User.DoesNotExist:
        return None


consume_ticket_and_get_active_user = database_sync_to_async(
    _consume_ticket_and_get_active_user,
    thread_sensitive=False,
)


async def consume_ticket(ticket):
    """Atomically consume a short-lived ticket and load its active user."""
    if not ticket:
        return AnonymousUser()

    digest = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
    key = f"ws-ticket:{digest}"
    try:
        # Consume the cache ticket and load the current active account in one
        # database-safe worker call. Cache.add remains atomic for LocMem/Redis.
        user = await consume_ticket_and_get_active_user(key)
        return user if user is not None else AnonymousUser()
    except Exception:
        logger.exception("WebSocket ticket authentication failed")
        return AnonymousUser()


class QueryStringJWTAuthMiddleware:
    """Authenticate WebSockets using one-use tickets, never access JWTs."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        try:
            query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
            ticket = (query.get("ticket") or [None])[0]
            user = await consume_ticket(ticket)
        except Exception:
            logger.exception("Invalid WebSocket authentication request")
            user = AnonymousUser()

        authenticated_scope = dict(scope)
        authenticated_scope["user"] = user
        return await self.inner(authenticated_scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return QueryStringJWTAuthMiddleware(inner)
