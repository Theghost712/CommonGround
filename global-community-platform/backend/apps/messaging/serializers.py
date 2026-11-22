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

    class Meta:
        model = Message
        fields = [
            "id", "conversation", "sender", "sender_username", "sender_display_name",
            "body", "created_at", "edited_at", "is_edited", "is_deleted", "read_by", "read_count",
        ]
        read_only_fields = fields

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
            "id", "conversation_type", "title", "display_title", "created_by",
            "members", "other_user", "last_message", "unread_count", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_members(self, obj):
        memberships = obj.memberships.filter(is_active=True).select_related("user")
        return ConversationMemberSerializer(memberships, many=True).data

    def get_last_message(self, obj):
        message = obj.messages.select_related("sender").order_by("-created_at", "-id").first()
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
