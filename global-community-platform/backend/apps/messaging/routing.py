from django.urls import re_path

from .consumers import ChatConsumer
from .presence_consumer import PresenceConsumer


websocket_urlpatterns = [
    # Chat WebSocket
    re_path(
        r"^ws/chat/(?P<conversation_id>[0-9]+)/$",
        ChatConsumer.as_asgi(),
    ),

    # Global Presence WebSocket
    re_path(
        r"^ws/presence/$",
        PresenceConsumer.as_asgi(),
    ),
]
