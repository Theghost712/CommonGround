import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from .models import Conversation, ConversationMember, Message, MessageReadReceipt
from .serializers import MessageSerializer
from apps.notifications.services import notify_chat_message


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user", AnonymousUser())
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return
        if not await self.is_member():
            await self.close(code=4403)
            return

        self.group_name = f"chat_{self.conversation_id}"
        self.user_group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.group_name, {
            "type": "chat.event",
            "data": {"type": "presence.check", "requester": self.channel_name},
        })
        await self.channel_layer.group_send(self.group_name, {
            "type": "chat.event",
            "data": {"type": "presence", "user_id": self.user.id, "username": self.user.username, "status": "online"},
        })

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_send(self.group_name, {
                "type": "chat.event",
                "data": {"type": "presence", "user_id": self.user.id, "username": self.user.username, "status": "offline"},
            })
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            if hasattr(self, "user_group_name"):
                await self.channel_layer.group_discard(self.user_group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not await self.is_member():
            await self.close(code=4403)
            return
        event_type = content.get("type")
        if event_type == "typing":
            await self.channel_layer.group_send(self.group_name, {
                "type": "chat.event",
                "data": {
                    "type": "typing", "user_id": self.user.id,
                    "username": self.user.username, "is_typing": bool(content.get("is_typing", True)),
                },
            })
            return

        if event_type == "message":
            now = time.monotonic()
            recent = [stamp for stamp in getattr(self, "message_timestamps", []) if now - stamp < 10]
            if len(recent) >= 20:
                await self.send_json({"type": "error", "detail": "You are sending messages too quickly. Please slow down."})
                self.message_timestamps = recent
                return
            recent.append(now)
            self.message_timestamps = recent
            body = str(content.get("body", "")).strip()
            if not body:
                await self.send_json({"type": "error", "detail": "Message cannot be empty."})
                return
            if len(body) > 4000:
                await self.send_json({"type": "error", "detail": "Message is too long (maximum 4000 characters)."})
                return
            if await self.chat_blocked():
                await self.send_json({"type": "error", "detail": "You can't message this account."})
                return
            message_data = await self.create_message(body)
            if message_data is None:
                await self.send_json({"type": "error", "detail": "You are no longer a member of this conversation."})
                await self.close(code=4403)
                return
            await self.channel_layer.group_send(self.group_name, {
                "type": "chat.event", "data": {"type": "message.created", "message": message_data},
            })
            return

        if event_type == "mark_read":
            receipt_data = await self.mark_conversation_read()
            await self.channel_layer.group_send(self.group_name, {
                "type": "chat.event",
                "data": {"type": "message.read", **receipt_data},
            })
            return

        await self.send_json({"type": "error", "detail": "Unsupported WebSocket event."})

    async def user_event(self, event):
        data = event.get("data", {})
        if data.get("type") == "membership.revoked" and str(data.get("conversation_id")) == str(self.conversation_id):
            await self.send_json({"type": "error", "detail": "Your access to this conversation was removed."})
            await self.close(code=4403)

    async def chat_event(self, event):
        data = event.get("data", {})
        if data.get("type") == "presence.check":
            requester = data.get("requester")
            if requester and requester != self.channel_name:
                await self.channel_layer.send(requester, {
                    "type": "chat.event",
                    "data": {"type": "presence", "user_id": self.user.id, "username": self.user.username, "status": "online"},
                })
            return
        # Do not echo typing events back to their sender.
        if data.get("type") == "typing" and data.get("user_id") == self.user.id:
            return
        await self.send_json(data)

    @database_sync_to_async
    def is_member(self):
        return ConversationMember.objects.filter(
            conversation_id=self.conversation_id, user=self.user, is_active=True
        ).exists()

    @database_sync_to_async
    def create_message(self, body):
        membership = ConversationMember.objects.filter(
            conversation_id=self.conversation_id, user=self.user, is_active=True
        ).first()
        if not membership:
            return None
        message = Message.objects.create(
            conversation_id=self.conversation_id, sender=self.user, body=body
        )
        MessageReadReceipt.objects.get_or_create(message=message, user=self.user)
        Conversation.objects.filter(pk=self.conversation_id).update(updated_at=timezone.now())
        message = Message.objects.select_related("sender", "conversation").get(pk=message.pk)
        notify_chat_message(message)
        return MessageSerializer(message).data

    @database_sync_to_async
    def chat_blocked(self):
        from .services import direct_chat_blocked

        return direct_chat_blocked(self.conversation_id, self.user)

    @database_sync_to_async
    def mark_conversation_read(self):
        membership = ConversationMember.objects.get(
            conversation_id=self.conversation_id, user=self.user, is_active=True
        )
        now = timezone.now()
        unread = Message.objects.filter(
            conversation_id=self.conversation_id,
            deleted_at__isnull=True,
        ).exclude(sender=self.user)
        unread_ids = list(unread.values_list("id", flat=True))
        MessageReadReceipt.objects.bulk_create(
            [MessageReadReceipt(message_id=message_id, user=self.user) for message_id in unread_ids],
            ignore_conflicts=True,
        )
        membership.last_read_at = now
        membership.save(update_fields=["last_read_at"])
        return {"user_id": self.user.id, "username": self.user.username, "message_ids": unread_ids}
