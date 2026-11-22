from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from .presence import (
    user_connected,
    user_disconnected,
    get_presence_snapshot,
)


class PresenceConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        self.user = self.scope.get("user", AnonymousUser())

        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        self.group_name = "global_presence"
        self.presence_registered = False

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )

        await self.accept()

        became_online = await user_connected(self.user.id)
        self.presence_registered = True

        # Send the current users' presence information.
        snapshot = await get_presence_snapshot()

        await self.send_json({
            "type": "presence.snapshot",
            "presences": snapshot,
        })

        await self.send_json({
            "type": "presence.connected",
            "user_id": self.user.id,
            "status": "online",
        })

        # Notify all connected users when this user first comes online.
        if became_online:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "presence.event",
                    "data": {
                        "type": "presence.update",
                        "user_id": self.user.id,
                        "username": self.user.username,
                        "status": "online",
                        "last_seen": None,
                    },
                },
            )

    async def disconnect(self, close_code):
        if not hasattr(self, "group_name"):
            return

        became_offline = False

        if getattr(self, "presence_registered", False):
            became_offline = await user_disconnected(
                self.user.id
            )

        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name,
        )

        if became_offline:
            from django.utils import timezone

            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "presence.event",
                    "data": {
                        "type": "presence.update",
                        "user_id": self.user.id,
                        "username": self.user.username,
                        "status": "offline",
                        "last_seen": timezone.now().isoformat(),
                    },
                },
            )

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def presence_event(self, event):
        await self.send_json(event.get("data", {}))
