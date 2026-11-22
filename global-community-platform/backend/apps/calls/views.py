from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.messaging.models import Conversation, ConversationMember
from apps.messaging.services import direct_chat_blocked

from .models import Call
from .services import busy, call_data, expire_stale_calls, finish, ice_servers, push


def error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)


class StartCallView(APIView):
    """POST {conversation_id, kind: audio|video}: ring the other person in a one-to-one chat."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "calls"

    def post(self, request):
        expire_stale_calls()
        kind = request.data.get("kind", Call.AUDIO)
        if kind not in (Call.AUDIO, Call.VIDEO):
            return error("Choose a voice or video call.")
        conversation = Conversation.objects.filter(
            pk=request.data.get("conversation_id"), memberships__user=request.user, memberships__is_active=True,
        ).first()
        if conversation is None:
            return error("Conversation not found.", status.HTTP_404_NOT_FOUND)
        if conversation.conversation_type != Conversation.DIRECT:
            return error("Calls work in one-to-one chats.")
        other = ConversationMember.objects.filter(conversation=conversation, is_active=True).exclude(user=request.user).select_related("user").first()
        if other is None or not other.user.is_active:
            return error("This person can't be called.")
        if direct_chat_blocked(conversation.pk, request.user):
            return error("You can't call this person.", status.HTTP_403_FORBIDDEN)
        with transaction.atomic():
            if busy(request.user):
                return error("You're already in a call.", status.HTTP_409_CONFLICT)
            if busy(other.user):
                return error(f"{other.user.username} is on another call.", status.HTTP_409_CONFLICT)
            call = Call.objects.create(conversation=conversation, caller=request.user, callee=other.user, kind=kind)
        call = Call.objects.select_related("caller", "callee").get(pk=call.pk)
        push(call.callee_id, {"type": "call.incoming", "call": call_data(call)})
        return Response({"call": call_data(call), "ice_servers": ice_servers(request.user)}, status=status.HTTP_201_CREATED)


class CallActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_call(self, request, pk):
        call = get_object_or_404(Call.objects.select_related("caller", "callee", "conversation"), pk=pk)
        if not call.involves(request.user):
            return None
        return call


class AcceptCallView(CallActionView):
    def post(self, request, pk):
        call = self.get_call(request, pk)
        if call is None or call.callee_id != request.user.pk:
            return error("Call not found.", status.HTTP_404_NOT_FOUND)
        device = str(request.data.get("device_id", ""))[:64]
        updated = Call.objects.filter(pk=call.pk, status=Call.RINGING).update(status=Call.ACCEPTED, answered_at=timezone.now(), answered_device=device)
        if not updated:
            return error("This call has already ended.", status.HTTP_409_CONFLICT)
        call.refresh_from_db()
        data = call_data(call)
        for user_id in (call.caller_id, call.callee_id):
            push(user_id, {"type": "call.update", "call": data})
        return Response({"call": data, "ice_servers": ice_servers(request.user)})


class DeclineCallView(CallActionView):
    def post(self, request, pk):
        call = self.get_call(request, pk)
        if call is None or call.callee_id != request.user.pk:
            return error("Call not found.", status.HTTP_404_NOT_FOUND)
        if call.status != Call.RINGING:
            return error("This call has already ended.", status.HTTP_409_CONFLICT)
        return Response({"call": call_data(finish(call, Call.DECLINED, by=request.user))})


class EndCallView(CallActionView):
    """Hang up (or cancel while ringing). {failed: true} records a connection failure."""

    def post(self, request, pk):
        call = self.get_call(request, pk)
        if call is None:
            return error("Call not found.", status.HTTP_404_NOT_FOUND)
        if call.status not in Call.LIVE:
            return Response({"call": call_data(call)})
        if call.status == Call.RINGING:
            outcome = Call.CANCELLED if request.user.pk == call.caller_id else Call.DECLINED
        else:
            outcome = Call.FAILED if request.data.get("failed") else Call.ENDED
        return Response({"call": call_data(finish(call, outcome, by=request.user))})


class ActiveCallView(APIView):
    """The live call you're part of, if any (a reloaded tab picks a ringing call back up)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        expire_stale_calls()
        from django.db.models import Q

        call = Call.objects.filter(Q(caller=request.user) | Q(callee=request.user), status__in=Call.LIVE).select_related("caller", "callee").first()
        return Response({"call": call_data(call) if call else None})
