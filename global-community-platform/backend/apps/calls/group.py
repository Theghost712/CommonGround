"""Group calls in group chats.

Signalling: whoever joins sends a WebRTC offer to everyone already in the call
(so two people never offer to each other at once). Offers, answers and ICE
candidates travel over the per-user calls socket as `group_signal` frames and
are forwarded only between active participants of the same call.

Presence: each participant's tab sends a heartbeat every ~20 s. A participant
silent for HEARTBEAT_TIMEOUT is dropped; the call ends when nobody is left.
"""

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.messaging.models import Conversation, ConversationMember

from .models import Call, GroupCall, GroupCallParticipant
from .services import _iso, ice_servers, push

HEARTBEAT_TIMEOUT = timedelta(seconds=60)
MAX_CALL_AGE = timedelta(hours=6)


def person(user):
    return {"id": user.pk, "username": user.username, "display_name": user.get_full_name() or user.username}


def active_participants(call):
    return call.participants.filter(left_at__isnull=True).select_related("user")


def group_call_data(call):
    return {
        "id": call.id, "conversation_id": call.conversation_id, "kind": call.kind, "status": call.status,
        "started_by": person(call.started_by), "created_at": _iso(call.created_at), "ended_at": _iso(call.ended_at),
        "participants": [
            {**person(p.user), "device_id": p.device_id, "joined_at": _iso(p.joined_at)}
            for p in (active_participants(call) if call.status == GroupCall.LIVE else [])
        ],
        "max_participants": settings.GROUP_CALL_MAX_PARTICIPANTS,
    }


def member_ids(conversation_id):
    return list(ConversationMember.objects.filter(conversation_id=conversation_id, is_active=True).values_list("user_id", flat=True))


def broadcast(call, event_type="group_call.update"):
    """Tell every member of the chat (in or out of the call) what the call looks like now."""
    data = group_call_data(call)
    for user_id in member_ids(call.conversation_id):
        push(user_id, {"type": event_type, "call": data})
    return data


def in_group_call(user):
    return GroupCallParticipant.objects.filter(user=user, left_at__isnull=True, call__status=GroupCall.LIVE).exists()


def end_call(call):
    """Close a live group call and leave a line in the chat."""
    now = timezone.now()
    if not GroupCall.objects.filter(pk=call.pk, status=GroupCall.LIVE).update(status=GroupCall.ENDED, ended_at=now):
        return
    call.participants.filter(left_at__isnull=True).update(left_at=now)
    call.refresh_from_db()
    broadcast(call)
    from apps.messaging.services import send_message

    seconds = int((call.ended_at - call.created_at).total_seconds())
    label = "Group video call" if call.kind == Call.VIDEO else "Group voice call"
    send_message(call.conversation, call.started_by, f"📞 {label} · {seconds // 60}:{seconds % 60:02d}")


def leave(call, user):
    now = timezone.now()
    changed = call.participants.filter(user=user, left_at__isnull=True).update(left_at=now)
    if not changed:
        return
    if not active_participants(call).exists():
        end_call(call)
    else:
        broadcast(call)


def expire_stale_group_calls():
    """Drop participants whose tab stopped sending heartbeats; end empty or ancient calls."""
    now = timezone.now()
    stale = GroupCallParticipant.objects.filter(left_at__isnull=True, call__status=GroupCall.LIVE, last_seen__lt=now - HEARTBEAT_TIMEOUT)
    touched = set(stale.values_list("call_id", flat=True))
    stale.update(left_at=now)
    for call in GroupCall.objects.filter(status=GroupCall.LIVE).filter(Q(pk__in=touched) | Q(created_at__lt=now - MAX_CALL_AGE)).select_related("conversation", "started_by"):
        if call.created_at < now - MAX_CALL_AGE or not active_participants(call).exists():
            end_call(call)
        else:
            broadcast(call)


def error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)


class GroupCallStartView(APIView):
    """POST {conversation_id, kind, device_id}: start a call in a group chat, or join
    the one already running there. Returns {call, ice_servers, joined_as}."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "calls"

    def post(self, request):
        from .services import busy

        expire_stale_group_calls()
        kind = request.data.get("kind", Call.AUDIO)
        if kind not in (Call.AUDIO, Call.VIDEO):
            return error("Choose a voice or video call.")
        device = str(request.data.get("device_id", ""))[:64]
        conversation = Conversation.objects.filter(
            pk=request.data.get("conversation_id"), memberships__user=request.user, memberships__is_active=True,
        ).first()
        if conversation is None:
            return error("Conversation not found.", status.HTTP_404_NOT_FOUND)
        if conversation.conversation_type != Conversation.GROUP:
            return error("Group calls work in group chats.")
        if busy(request.user):
            return error("You're already in a call.", status.HTTP_409_CONFLICT)
        started = False
        try:
            with transaction.atomic():
                other_call = GroupCallParticipant.objects.filter(user=request.user, left_at__isnull=True, call__status=GroupCall.LIVE).exclude(call__conversation=conversation).exists()
                if other_call:
                    return error("You're already in another group call.", status.HTTP_409_CONFLICT)
                call = GroupCall.objects.select_for_update().filter(conversation=conversation, status=GroupCall.LIVE).first()
                if call is None:
                    call = GroupCall.objects.create(conversation=conversation, started_by=request.user, kind=kind)
                    started = True
                seat = call.participants.filter(user=request.user, left_at__isnull=True).first()
                if seat is not None:
                    # Joining again from another tab/device: that tab takes over.
                    seat.device_id = device
                    seat.last_seen = timezone.now()
                    seat.save(update_fields=["device_id", "last_seen"])
                else:
                    if call.participants.filter(left_at__isnull=True).count() >= settings.GROUP_CALL_MAX_PARTICIPANTS:
                        return error(f"This call is full ({settings.GROUP_CALL_MAX_PARTICIPANTS} people).", status.HTTP_409_CONFLICT)
                    GroupCallParticipant.objects.create(call=call, user=request.user, device_id=device)
        except IntegrityError:  # two people started a call in the same chat at the same moment
            return error("A call just started in this chat. Tap join to enter it.", status.HTTP_409_CONFLICT)
        call = GroupCall.objects.select_related("started_by", "conversation").get(pk=call.pk)
        data = broadcast(call, "group_call.started" if started else "group_call.update")
        if started:
            self.ring_members(call, request.user)
        return Response({"call": data, "ice_servers": ice_servers(request.user)}, status=status.HTTP_201_CREATED if started else status.HTTP_200_OK)

    def ring_members(self, call, starter):
        from apps.notifications.push import send_push_to_user

        name = starter.get_full_name() or starter.username
        chat = call.conversation.title or "your group"
        for user_id in member_ids(call.conversation_id):
            if user_id == starter.pk:
                continue
            send_push_to_user(user_id, {
                "title": f"{name} started a group call", "body": f"Tap to join the {'video' if call.kind == Call.VIDEO else 'voice'} call in {chat}.",
                "url": f"/messages?conversation={call.conversation_id}", "tag": f"chat-{call.conversation_id}", "kind": "call",
            })


class GroupCallMixin:
    permission_classes = [permissions.IsAuthenticated]

    def get_call(self, request, pk):
        return GroupCall.objects.select_related("started_by", "conversation").filter(
            pk=pk, conversation__memberships__user=request.user, conversation__memberships__is_active=True,
        ).first()


class GroupCallLeaveView(GroupCallMixin, APIView):
    def post(self, request, pk):
        call = self.get_call(request, pk)
        if call is None:
            return error("Call not found.", status.HTTP_404_NOT_FOUND)
        device = str(request.data.get("device_id", ""))[:64]
        seat = call.participants.filter(user=request.user, left_at__isnull=True).first()
        # A tab that was replaced by another device must not hang up the new one.
        if seat is not None and (not device or not seat.device_id or seat.device_id == device):
            leave(call, request.user)
        call.refresh_from_db()
        return Response({"call": group_call_data(call)})


class GroupCallHeartbeatView(GroupCallMixin, APIView):
    """POST {device_id}: "still here". 410 when you're no longer in the call."""

    def post(self, request, pk):
        call = self.get_call(request, pk)
        if call is None:
            return error("Call not found.", status.HTTP_404_NOT_FOUND)
        device = str(request.data.get("device_id", ""))[:64]
        updated = call.participants.filter(user=request.user, left_at__isnull=True, device_id=device, call__status=GroupCall.LIVE).update(last_seen=timezone.now())
        expire_stale_group_calls()
        call.refresh_from_db()
        if not updated:
            return Response({"call": group_call_data(call), "detail": "You're not in this call any more."}, status=status.HTTP_410_GONE)
        return Response({"call": group_call_data(call)})


class GroupCallActiveView(APIView):
    """GET: live group calls in the chats you belong to (?conversation_id= narrows it)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        expire_stale_group_calls()
        calls = GroupCall.objects.filter(
            status=GroupCall.LIVE, conversation__memberships__user=request.user, conversation__memberships__is_active=True,
        ).select_related("started_by")
        conversation_id = request.query_params.get("conversation_id")
        if conversation_id:
            if not str(conversation_id).isdigit():
                return error("Invalid conversation.")
            calls = calls.filter(conversation_id=conversation_id)
        return Response({"calls": [group_call_data(call) for call in calls[:50]]})


def group_signal_target(call_id, sender_id, sender_device, target_id):
    """The device to forward a group signal to, or None unless both people are in
    the call (and the sender is writing from the tab that joined)."""
    seats = dict(GroupCallParticipant.objects.filter(
        call_id=call_id, call__status=GroupCall.LIVE, left_at__isnull=True, user_id__in=[sender_id, target_id],
    ).values_list("user_id", "device_id"))
    if sender_id == target_id or sender_id not in seats or target_id not in seats:
        return None
    if seats[sender_id] and seats[sender_id] != sender_device:
        return None
    return seats[target_id]
