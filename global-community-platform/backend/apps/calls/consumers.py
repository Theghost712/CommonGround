from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from .services import clean_signal, user_group

MAX_SIGNALS_PER_CONNECTION = 2000


class CallsConsumer(AsyncJsonWebsocketConsumer):
    """Per-user socket: rings for incoming calls and relays WebRTC offers/answers/ICE
    candidates between the two people in a live call. Nothing else is forwarded."""

    async def connect(self):
        self.user = self.scope.get("user", AnonymousUser())
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return
        self.group_name = user_group(self.user.id)
        self.signals = 0
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "calls.connected"})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        kind = content.get("type")
        if kind == "ping":
            await self.send_json({"type": "pong"})
            return
        if kind != "signal":
            return
        self.signals += 1
        if self.signals > MAX_SIGNALS_PER_CONNECTION:
            await self.close(code=4429)
            return
        data = clean_signal(content.get("data"))
        try:
            call_id = int(content.get("call_id"))
        except (TypeError, ValueError):
            return
        if data is None:
            return
        other_id = await self.peer_for(call_id)
        if other_id is None:
            await self.send_json({"type": "call.error", "call_id": call_id, "detail": "This call is not active."})
            return
        await self.channel_layer.group_send(user_group(other_id), {"type": "call.event", "data": {
            "type": "call.signal", "call_id": call_id, "data": data, "from": self.user.id,
            "device_id": str(content.get("device_id", ""))[:64],
        }})

    @database_sync_to_async
    def peer_for(self, call_id):
        from .models import Call

        call = Call.objects.filter(pk=call_id, status=Call.ACCEPTED).values("caller_id", "callee_id").first()
        if call is None or self.user.id not in (call["caller_id"], call["callee_id"]):
            return None
        return call["callee_id"] if self.user.id == call["caller_id"] else call["caller_id"]

    async def call_event(self, event):
        await self.send_json(event.get("data", {}))
