from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from .models import Conversation


def broadcast_message(message_data, conversation_id):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"chat_{conversation_id}",
        {"type": "chat.event", "data": {"type": "message.created", "message": message_data}},
    )


def broadcast_read(conversation_id, data):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"chat_{conversation_id}",
        {"type": "chat.event", "data": {"type": "message.read", **data}},
    )


def touch_conversation(conversation_id):
    Conversation.objects.filter(pk=conversation_id).update(updated_at=timezone.now())



def broadcast_membership_revoked(user_id, conversation_id):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"user_{user_id}",
        {"type": "user.event", "data": {"type": "membership.revoked", "conversation_id": conversation_id}},
    )


def get_or_create_direct_conversation(user, other):
    """The one-to-one conversation between two users, created if it does not exist yet."""
    from django.db import transaction

    from .models import Conversation, ConversationMember

    with transaction.atomic():
        candidates = (
            Conversation.objects.filter(conversation_type=Conversation.DIRECT, memberships__user=user, memberships__is_active=True)
            .distinct()
            .prefetch_related("memberships")
        )
        for candidate in candidates:
            ids = {m.user_id for m in candidate.memberships.all() if m.is_active}
            if ids == {user.id, other.id}:
                return candidate
        conversation = Conversation.objects.create(conversation_type=Conversation.DIRECT, created_by=user)
        ConversationMember.objects.bulk_create([
            ConversationMember(conversation=conversation, user=user, role=ConversationMember.OWNER),
            ConversationMember(conversation=conversation, user=other),
        ])
        return conversation


def send_message(conversation, sender, body):
    """Create a chat message, broadcast it live and notify the other members."""
    from apps.notifications.services import notify_chat_message

    from .models import Message, MessageReadReceipt
    from .serializers import MessageSerializer

    message = Message.objects.create(conversation=conversation, sender=sender, body=body)
    MessageReadReceipt.objects.get_or_create(message=message, user=sender)
    touch_conversation(conversation.id)
    message = Message.objects.select_related("sender", "conversation").get(pk=message.pk)
    notify_chat_message(message)
    broadcast_message(MessageSerializer(message).data, conversation.id)
    return message


def direct_chat_blocked(conversation_id, user):
    """True when this is a one-to-one chat and either person has blocked the other."""
    from apps.safety.services import is_blocked_between

    from .models import Conversation, ConversationMember

    conversation = Conversation.objects.filter(pk=conversation_id).first()
    if conversation is None or conversation.conversation_type != Conversation.DIRECT:
        return False
    other = ConversationMember.objects.filter(conversation_id=conversation_id).exclude(user=user).select_related("user").first()
    return bool(other and is_blocked_between(user, other.user))
