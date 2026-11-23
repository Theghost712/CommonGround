import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Call

RING_SECONDS = 45


def user_group(user_id):
    return f"calls_user_{user_id}"


def push(user_id, data):
    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(user_group(user_id), {"type": "call.event", "data": data})


def _iso(value):
    return value.isoformat() if value else None


def call_data(call):
    """JSON-safe call info. It travels through the channel layer (msgpack with Redis),
    which can't carry datetime objects, so times are ISO strings."""
    return {
        "id": call.id, "conversation_id": call.conversation_id, "kind": call.kind, "status": call.status,
        "caller": {"id": call.caller_id, "username": call.caller.username, "display_name": call.caller.get_full_name() or call.caller.username},
        "callee": {"id": call.callee_id, "username": call.callee.username, "display_name": call.callee.get_full_name() or call.callee.username},
        "answered_device": call.answered_device, "created_at": _iso(call.created_at), "answered_at": _iso(call.answered_at), "ended_at": _iso(call.ended_at),
    }


def expire_stale_calls():
    """Ringing calls nobody answered become missed; accepted calls left open for hours are closed."""
    now = timezone.now()
    for call in Call.objects.filter(status=Call.RINGING, created_at__lt=now - timedelta(seconds=RING_SECONDS + 15)).select_related("caller", "callee", "conversation"):
        finish(call, Call.MISSED, notify=True)
    Call.objects.filter(status=Call.ACCEPTED, answered_at__lt=now - timedelta(hours=6)).update(status=Call.ENDED, ended_at=now)


def busy(user):
    """In a live one-to-one call (ringing or answered)? Group calls: see group.in_group_call."""
    return Call.objects.filter(Q(caller=user) | Q(callee=user), status__in=Call.LIVE,
                               created_at__gte=timezone.now() - timedelta(hours=6)).exists()


def busy_anywhere(user):
    from .group import in_group_call

    return busy(user) or in_group_call(user)


def finish(call, status, notify=True, by=None):
    """Close a live call, tell both people, and leave a line in the chat like WhatsApp does."""
    if call.status not in Call.LIVE:
        return call
    call.status = status
    call.ended_at = timezone.now()
    call.save(update_fields=["status", "ended_at"])
    data = call_data(call)
    for user_id in (call.caller_id, call.callee_id):
        push(user_id, {"type": "call.update", "call": data, "by": by.pk if by else None})
    if notify:
        log_in_chat(call)
    return call


def log_in_chat(call):
    from apps.messaging.services import send_message

    label = "Video call" if call.kind == Call.VIDEO else "Voice call"
    if call.status == Call.ENDED and call.answered_at:
        seconds = int((call.ended_at - call.answered_at).total_seconds())
        body = f"📞 {label} · {seconds // 60}:{seconds % 60:02d}"
    elif call.status in (Call.MISSED, Call.CANCELLED):
        body = f"📞 Missed {label.lower()}"
    elif call.status == Call.DECLINED:
        body = f"📞 {label} declined"
    else:
        body = f"📞 {label} couldn't connect"
    send_message(call.conversation, call.caller, body)


def ice_servers(user):
    """STUN for discovery plus, when configured, short-lived TURN credentials (coturn
    'use-auth-secret' / TURN REST API), so calls work behind strict NATs."""
    servers = [{"urls": url} for url in settings.WEBRTC_STUN_URLS]
    if settings.TURN_URLS and settings.TURN_SECRET:
        expires = int(time.time()) + settings.TURN_CREDENTIAL_TTL
        username = f"{expires}:{user.pk}"
        digest = hmac.new(settings.TURN_SECRET.encode(), username.encode(), hashlib.sha1).digest()
        servers.append({"urls": settings.TURN_URLS, "username": username, "credential": base64.b64encode(digest).decode()})
    elif settings.TURN_URLS and settings.TURN_USERNAME and settings.TURN_CREDENTIAL:
        servers.append({"urls": settings.TURN_URLS, "username": settings.TURN_USERNAME, "credential": settings.TURN_CREDENTIAL})
    return servers


SIGNAL_KEYS = {"sdp", "candidate"}
MAX_SIGNAL_BYTES = 64 * 1024


def clean_signal(data):
    """Only forward WebRTC session descriptions and ICE candidates, and nothing huge."""
    if not isinstance(data, dict) or not data or not set(data) <= SIGNAL_KEYS:
        return None
    if len(json.dumps(data)) > MAX_SIGNAL_BYTES:
        return None
    sdp = data.get("sdp")
    if sdp is not None and (not isinstance(sdp, dict) or sdp.get("type") not in ("offer", "answer") or not isinstance(sdp.get("sdp"), str)):
        return None
    return data
