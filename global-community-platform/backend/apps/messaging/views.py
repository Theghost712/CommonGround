from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Conversation, ConversationMember, Message, MessageReadReceipt
from .serializers import ChatUserSerializer, ConversationMemberSerializer, ConversationSerializer, MessageSerializer
from .services import broadcast_membership_revoked, broadcast_message, broadcast_read, touch_conversation
from apps.notifications.services import notify_chat_message

User = get_user_model()


class ChatUserSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response({"results": [], "detail": "Enter at least two characters to search."})
        from apps.safety.services import blocked_user_ids

        users = User.objects.filter(is_active=True).exclude(pk=request.user.pk).exclude(pk__in=blocked_user_ids(request.user)).filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        ).order_by("username")[:15]
        return Response({"results": ChatUserSerializer(users, many=True).data})


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Conversation.objects.filter(
            memberships__user=self.request.user,
            memberships__is_active=True,
        ).distinct().prefetch_related("memberships__user", "messages__sender")

    def create(self, request, *args, **kwargs):
        """Create a group conversation. Use start-direct for one-to-one chats."""
        title = str(request.data.get("title", "")).strip()
        raw_ids = request.data.get("member_ids", [])
        if not isinstance(raw_ids, list):
            raise ValidationError({"member_ids": "Provide member_ids as a list of user IDs."})
        try:
            member_ids = {int(value) for value in raw_ids}
        except (TypeError, ValueError):
            raise ValidationError({"member_ids": "Every member ID must be an integer."})
        member_ids.discard(request.user.id)
        if not title:
            raise ValidationError({"title": "A group name is required."})
        if len(title) > 120:
            raise ValidationError({"title": "Group name cannot exceed 120 characters."})
        if not member_ids:
            raise ValidationError({"member_ids": "Add at least one other participant."})
        if len(member_ids) > 99:
            raise ValidationError({"member_ids": "A group can have at most 100 participants."})
        users = list(User.objects.filter(pk__in=member_ids, is_active=True))
        if len(users) != len(member_ids):
            raise ValidationError({"member_ids": "One or more selected users could not be found."})

        with transaction.atomic():
            conversation = Conversation.objects.create(
                conversation_type=Conversation.GROUP,
                title=title,
                created_by=request.user,
            )
            ConversationMember.objects.create(
                conversation=conversation, user=request.user, role=ConversationMember.OWNER
            )
            ConversationMember.objects.bulk_create([
                ConversationMember(conversation=conversation, user=user, role=ConversationMember.MEMBER)
                for user in users
            ])
        serializer = self.get_serializer(conversation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="start-direct")
    def start_direct(self, request):
        try:
            other_user_id = int(request.data.get("user_id"))
        except (TypeError, ValueError):
            raise ValidationError({"user_id": "Provide a valid user ID."})
        if other_user_id == request.user.id:
            raise ValidationError({"user_id": "You cannot start a conversation with yourself."})
        other_user = get_object_or_404(User, pk=other_user_id, is_active=True)
        from apps.safety.services import is_blocked_between

        if is_blocked_between(request.user, other_user):
            raise PermissionDenied("You can't message this account.")

        with transaction.atomic():
            candidates = Conversation.objects.filter(
                conversation_type=Conversation.DIRECT,
                memberships__user=request.user,
                memberships__is_active=True,
            ).distinct().prefetch_related("memberships")
            conversation = None
            for candidate in candidates:
                ids = set(candidate.memberships.filter(is_active=True).values_list("user_id", flat=True))
                if ids == {request.user.id, other_user.id}:
                    conversation = candidate
                    break
            if conversation is None:
                conversation = Conversation.objects.create(
                    conversation_type=Conversation.DIRECT,
                    created_by=request.user,
                )
                ConversationMember.objects.bulk_create([
                    ConversationMember(conversation=conversation, user=request.user, role=ConversationMember.OWNER),
                    ConversationMember(conversation=conversation, user=other_user),
                ])

        return Response(self.get_serializer(conversation).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        if request.method == "GET":
            queryset = (conversation.messages.filter(deleted_at__isnull=True).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
                        .select_related("sender", "shared_post__author").prefetch_related("read_receipts__user", "opens"))
            # Return the most recent 100 messages in chronological order.
            messages = list(queryset.order_by("-created_at", "-id")[:100])
            messages.reverse()
            return Response(MessageSerializer(messages, many=True).data)

        body = str(request.data.get("body", "")).strip()
        if not body:
            raise ValidationError({"body": "Message cannot be empty."})
        from .services import direct_chat_blocked

        if direct_chat_blocked(conversation.id, request.user):
            raise PermissionDenied("You can't message this account.")
        if len(body) > 4000:
            raise ValidationError({"body": "Message cannot exceed 4000 characters."})
        from .media import expiry_for

        message = Message.objects.create(conversation=conversation, sender=request.user, body=body, expires_at=expiry_for(conversation))
        MessageReadReceipt.objects.get_or_create(message=message, user=request.user)
        touch_conversation(conversation.id)
        message = Message.objects.select_related("sender", "conversation").get(pk=message.pk)
        notify_chat_message(message)
        data = MessageSerializer(message).data
        broadcast_message(data, conversation.id)
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        conversation = self.get_object()
        now = timezone.now()
        unread_ids = list(
            conversation.messages.filter(deleted_at__isnull=True)
            .exclude(sender=request.user)
            .exclude(read_receipts__user=request.user)
            .values_list("id", flat=True)
        )
        MessageReadReceipt.objects.bulk_create(
            [MessageReadReceipt(message_id=message_id, user=request.user) for message_id in unread_ids],
            ignore_conflicts=True,
        )
        membership = ConversationMember.objects.get(conversation=conversation, user=request.user, is_active=True)
        membership.last_read_at = now
        membership.save(update_fields=["last_read_at"])
        data = {"user_id": request.user.id, "username": request.user.username, "message_ids": unread_ids}
        broadcast_read(conversation.id, data)
        return Response({"marked_read": len(unread_ids), **data})

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        conversation = self.get_object()
        members = conversation.memberships.filter(is_active=True).select_related("user")
        return Response(ConversationMemberSerializer(members, many=True).data)

    @action(detail=True, methods=["post"], url_path="add-members")
    def add_members(self, request, pk=None):
        conversation = self.get_object()
        if conversation.conversation_type != Conversation.GROUP:
            raise ValidationError({"detail": "Participants can only be added to group conversations."})
        actor = conversation.memberships.get(user=request.user, is_active=True)
        if actor.role not in [ConversationMember.OWNER, ConversationMember.ADMIN]:
            raise PermissionDenied("Only group owners and administrators can add participants.")
        raw_ids = request.data.get("member_ids", [])
        if not isinstance(raw_ids, list):
            raise ValidationError({"member_ids": "Provide member_ids as a list."})
        ids = set()
        try:
            ids = {int(value) for value in raw_ids}
        except (TypeError, ValueError):
            raise ValidationError({"member_ids": "Every member ID must be an integer."})
        users = list(User.objects.filter(pk__in=ids, is_active=True))
        if len(users) != len(ids):
            raise ValidationError({"member_ids": "One or more users could not be found."})
        added = []
        for user in users:
            membership, created = ConversationMember.objects.get_or_create(
                conversation=conversation, user=user,
                defaults={"role": ConversationMember.MEMBER, "is_active": True},
            )
            was_inactive = not membership.is_active
            if was_inactive:
                membership.is_active = True
                membership.role = ConversationMember.MEMBER
                membership.save(update_fields=["is_active", "role"])
            if created or was_inactive:
                added.append(user.username)
        return Response({"added": added})

    @action(detail=True, methods=["post"], url_path="remove-member")
    def remove_member(self, request, pk=None):
        conversation = self.get_object()
        if conversation.conversation_type != Conversation.GROUP:
            raise ValidationError({"detail": "This action is only available for group conversations."})
        actor = conversation.memberships.get(user=request.user, is_active=True)
        if actor.role not in [ConversationMember.OWNER, ConversationMember.ADMIN]:
            raise PermissionDenied("Only group owners and administrators can remove participants.")
        try:
            target_id = int(request.data.get("user_id"))
        except (TypeError, ValueError):
            raise ValidationError({"user_id": "Provide a valid user ID."})
        target = get_object_or_404(conversation.memberships, user_id=target_id, is_active=True)
        if target.role == ConversationMember.OWNER:
            raise ValidationError({"detail": "The group owner cannot be removed."})
        if actor.role == ConversationMember.ADMIN and target.role == ConversationMember.ADMIN:
            raise PermissionDenied("Administrators cannot remove another administrator.")
        target.is_active = False
        target.save(update_fields=["is_active"])
        broadcast_membership_revoked(target_id, conversation.id)
        return Response({"removed": True, "user_id": target_id})

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        """Leave a group. If the owner leaves, the longest-standing admin (or member) takes over."""
        conversation = self.get_object()
        if conversation.conversation_type != Conversation.GROUP:
            raise ValidationError({"detail": "You can only leave group conversations."})
        with transaction.atomic():
            membership = conversation.memberships.select_for_update().get(user=request.user, is_active=True)
            was_owner = membership.role == ConversationMember.OWNER
            membership.is_active = False
            membership.role = ConversationMember.MEMBER
            membership.save(update_fields=["is_active", "role"])
            new_owner = None
            if was_owner:
                remaining = conversation.memberships.filter(is_active=True)
                successor = (
                    remaining.filter(role=ConversationMember.ADMIN).order_by("joined_at", "id").first()
                    or remaining.order_by("joined_at", "id").first()
                )
                if successor:
                    successor.role = ConversationMember.OWNER
                    successor.save(update_fields=["role"])
                    new_owner = successor.user_id
        broadcast_membership_revoked(request.user.id, conversation.id)
        return Response({"left": True, "new_owner_id": new_owner})
