from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Conversation, ConversationMember, Message, MessageReadReceipt

User = get_user_model()


class ChatUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "display_name", "avatar_url"]

    def get_display_name(self, obj):
        return obj.get_full_name().strip() or obj.username

    def get_avatar_url(self, obj):
        try:
            return obj.profile.avatar_url or None
        except Exception:
            return None


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    sender_display_name = serializers.SerializerMethodField()
    read_by = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()
    is_edited = serializers.SerializerMethodField()
    is_deleted = serializers.SerializerMethodField()
    media_url = serializers.SerializerMethodField()
    thumb_url = serializers.SerializerMethodField()
    opened_by = serializers.SerializerMethodField()
    shared_post = serializers.SerializerMethodField()
    preview = serializers.CharField(read_only=True)

    class Meta:
        model = Message
        fields = [
            "id", "conversation", "sender", "sender_username", "sender_display_name",
            "kind", "body", "preview", "media_url", "thumb_url", "width", "height", "duration_ms", "processing",
            "view_once", "opened_by", "shared_post", "expires_at",
            "created_at", "edited_at", "is_edited", "is_deleted", "read_by", "read_count",
        ]
        read_only_fields = fields

    def get_media_url(self, obj):
        from .media import media_url

        if obj.view_once or obj.deleted_at or obj.kind == Message.PHOTO and obj.processing == "failed":
            return ""
        return media_url(obj, "media")

    def get_thumb_url(self, obj):
        from .media import media_url

        return "" if obj.view_once or obj.deleted_at else media_url(obj, "thumb")

    def get_opened_by(self, obj):
        return list(obj.opens.values_list("user_id", flat=True)) if obj.view_once else []

    def get_shared_post(self, obj):
        post = obj.shared_post
        if post is None:
            return None
        first = post.attachments.order_by("created_at").first()
        thumb = ""
        if first is not None:
            from apps.discussions.images import image_url

            try:
                thumb = image_url(first, "thumb") if first.thumbnail else ""
            except Exception:
                thumb = ""
        return {"id": post.pk, "author": post.author.username, "title": post.title, "text": (post.body or "")[:200],
                "thumb_url": thumb, "is_video": bool(first and (first.content_type or "").startswith("video/"))}

    def get_sender_display_name(self, obj):
        return obj.sender.get_full_name().strip() or obj.sender.username

    def get_read_by(self, obj):
        users = User.objects.filter(chat_read_receipts__message=obj).exclude(pk=obj.sender_id).values_list("username", flat=True)
        return list(users)

    def get_read_count(self, obj):
        return obj.read_receipts.exclude(user_id=obj.sender_id).count()

    def get_is_edited(self, obj):
        return bool(obj.edited_at)

    def get_is_deleted(self, obj):
        return bool(obj.deleted_at)


class ConversationMemberSerializer(serializers.ModelSerializer):
    user = ChatUserSerializer(read_only=True)

    class Meta:
        model = ConversationMember
        fields = ["id", "user", "role", "joined_at", "last_read_at"]


class ConversationSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    display_title = serializers.SerializerMethodField()
    other_user = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id", "conversation_type", "title", "display_title", "created_by", "disappear_seconds",
            "members", "other_user", "last_message", "unread_count", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_members(self, obj):
        memberships = obj.memberships.filter(is_active=True).select_related("user")
        return ConversationMemberSerializer(memberships, many=True).data

    def get_last_message(self, obj):
        from django.db.models import Q
        from django.utils import timezone

        message = (obj.messages.select_related("sender").filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
                   .order_by("-created_at", "-id").first())
        return MessageSerializer(message).data if message else None

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0
        membership = obj.memberships.filter(user=request.user, is_active=True).first()
        if not membership:
            return 0
        messages = obj.messages.exclude(sender=request.user).filter(deleted_at__isnull=True)
        if membership.last_read_at:
            messages = messages.filter(created_at__gt=membership.last_read_at)
        return messages.count()

    def get_display_title(self, obj):
        if obj.conversation_type == Conversation.GROUP and obj.title:
            return obj.title
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            other = obj.memberships.filter(is_active=True).exclude(user=request.user).select_related("user").first()
            if other:
                return other.user.get_full_name().strip() or other.user.username
        return obj.title or "Direct conversation"

    def get_other_user(self, obj):
        if obj.conversation_type != Conversation.DIRECT:
            return None
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        membership = obj.memberships.filter(is_active=True).exclude(user=request.user).select_related("user").first()
        return ChatUserSerializer(membership.user).data if membership else None
