"""Web Push: notifications that reach a phone or computer even when CommonGround isn't open.

Setup (once): `python manage.py generate_vapid_keys`, then set VAPID_PUBLIC_KEY,
VAPID_PRIVATE_KEY and VAPID_SUBJECT (mailto:you@example.com). Without the keys,
push is simply off and /push/config/ says so.

Each browser that opts in registers a PushSubscription. Sends happen after the
database commit, on a small thread pool, so a slow push service never delays the
request that caused the notification. Subscriptions the push service reports as
gone (404/410) are deleted.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from .models import PushSubscription

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTIONS_PER_USER = 10
MAX_FAILURES = 5
PUSH_TTL_SECONDS = 24 * 3600
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webpush")


def push_enabled():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def _send_one(sub, payload):
    """Deliver to one device. `sub` is (pk, endpoint, p256dh, auth, failure_count).

    Touches the database only when something changes (gone, failing, recovered),
    so a busy chat doesn't hold extra connections from the small pool.
    """
    from pywebpush import WebPushException, webpush

    pk, endpoint, p256dh, auth, failures = sub
    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=PUSH_TTL_SECONDS,
            timeout=10,
        )
    except WebPushException as error:
        code = getattr(error.response, "status_code", None)
        _record_failure(pk, gone=code in (404, 410))
        if code not in (404, 410):
            logger.warning("Web push to subscription %s failed (%s): %s", pk, code, error)
        return False
    except Exception:  # network errors, bad keys: log, never raise into the app
        logger.exception("Web push to subscription %s failed", pk)
        _record_failure(pk)
        return False
    if failures:
        _db(lambda: PushSubscription.objects.filter(pk=pk).update(last_success_at=timezone.now(), failure_count=0))
    return True


def _db(action):
    # Worker threads tidy up their own connections. Inline (WEB_PUSH_SYNC) sends run
    # on the caller's connection, which may be inside a transaction: leave it alone.
    inline = getattr(settings, "WEB_PUSH_SYNC", False)
    if not inline:
        close_old_connections()
    try:
        action()
    finally:
        if not inline:
            close_old_connections()


def _record_failure(pk, gone=False):
    def action():
        if gone:
            PushSubscription.objects.filter(pk=pk).delete()
            return
        PushSubscription.objects.filter(pk=pk).update(failure_count=F("failure_count") + 1)
        PushSubscription.objects.filter(pk=pk, failure_count__gte=MAX_FAILURES).delete()
    _db(action)


def send_push_to_user(user_id, message):
    """Queue a push to every device of a user, after the current transaction commits.

    `message` is the JSON the service worker reads: {title, body, url, tag, kind, ...}.
    Returns the number of devices queued. WEB_PUSH_SYNC=True sends inline (tests).
    """
    if not push_enabled():
        return 0
    subs = list(PushSubscription.objects.filter(user_id=user_id).values_list("pk", "endpoint", "p256dh", "auth", "failure_count"))
    if not subs:
        return 0
    payload = json.dumps(message, separators=(",", ":"))[:3500]  # push services cap payloads near 4 KB

    def dispatch():
        for sub in subs:
            if getattr(settings, "WEB_PUSH_SYNC", False):
                _send_one(sub, payload)
            else:
                _executor.submit(_send_one, sub, payload)

    transaction.on_commit(dispatch)
    return len(subs)


def notification_message(notification):
    actor = notification.actor.username if notification.actor_id else None
    return {
        "title": notification.title,
        "body": notification.body[:240],
        "url": notification.target_url or "/notifications",
        # One visible notification per thread/topic: a new chat message replaces the last.
        "tag": f"chat-{notification.data['conversation_id']}" if notification.data.get("conversation_id") else f"n-{notification.pk}",
        "kind": notification.notification_type,
        "id": notification.pk,
        "actor": actor,
    }


# ---------------------------------------------------------------- API

ALLOWED_PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com", "push.services.mozilla.com", "notify.windows.com",
    "push.apple.com", "web.push.apple.com", "updates.push.services.mozilla.com",
)


def _valid_endpoint(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    extra = tuple(getattr(settings, "WEB_PUSH_EXTRA_HOSTS", ()))
    return parsed.scheme == "https" and any(host == s or host.endswith("." + s) for s in ALLOWED_PUSH_HOST_SUFFIXES + extra)


class SubscriptionSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=1000)
    keys = serializers.DictField(child=serializers.CharField(max_length=200))

    def validate_endpoint(self, value):
        # Only real browser push services: the server POSTs to this URL, so an
        # arbitrary one would let anyone make it send requests anywhere.
        if not _valid_endpoint(value):
            raise serializers.ValidationError("This isn't a browser push address.")
        return value

    def validate_keys(self, value):
        if not value.get("p256dh") or not value.get("auth"):
            raise serializers.ValidationError("p256dh and auth keys are required.")
        return value


class PushConfigView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({
            "enabled": push_enabled(),
            "public_key": settings.VAPID_PUBLIC_KEY if push_enabled() else "",
            "devices": PushSubscription.objects.filter(user=request.user).count(),
        })


class PushSubscribeView(APIView):
    """POST the browser's PushSubscription JSON ({endpoint, keys: {p256dh, auth}})."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "uploads"

    def post(self, request):
        if not push_enabled():
            return Response({"detail": "Push notifications aren't set up on this server."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        serializer = SubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            # The same browser may have belonged to someone else who signed out on it.
            PushSubscription.objects.update_or_create(endpoint=data["endpoint"], defaults={
                "user": request.user, "p256dh": data["keys"]["p256dh"], "auth": data["keys"]["auth"],
                "user_agent": request.headers.get("User-Agent", "")[:300], "failure_count": 0,
            })
            extra = PushSubscription.objects.filter(user=request.user).order_by("-created_at").values_list("pk", flat=True)[MAX_SUBSCRIPTIONS_PER_USER:]
            PushSubscription.objects.filter(pk__in=list(extra)).delete()
        return Response({"subscribed": True}, status=status.HTTP_201_CREATED)


class PushUnsubscribeView(APIView):
    """POST {endpoint}. Called when the user turns push off or signs out on this device."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        endpoint = str(request.data.get("endpoint", ""))
        deleted, _ = PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return Response({"removed": bool(deleted)})


class PushTestView(APIView):
    """POST: send a test notification to every device of the signed-in user."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "account_email"

    def post(self, request):
        count = send_push_to_user(request.user.pk, {
            "title": "CommonGround", "body": "Push notifications work on this device.",
            "url": "/notifications", "tag": "push-test", "kind": "system", "force": True,
        })
        if not count:
            return Response({"detail": "No device is set up for push yet."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": f"Sent to {count} device{'s' if count != 1 else ''}."})
